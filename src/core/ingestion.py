"""
Live data ingestion layer for Aviator Predictor.

Connects to Spribe's Aviator game WebSocket to capture resolved round data
in real-time (crash multiplier + server seed hash revealed post-round).

Architecture:
  - WebSocketListener:  Persistent async WS connection with auto-reconnect.
  - RoundParser:        Parses raw WS message JSON into structured RoundData.
  - DataPipeline:       Feeds parsed rounds into LivePredictor and logs to SQLite.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

# Spribe Aviator WebSocket endpoint (public — no auth required for read-only stream)
# Note: The actual endpoint path may vary per operator. This is the standard Spribe path.
AVIATOR_WS_URL = "wss://aviator-api.spribe.co/game-round"

RECONNECT_DELAY_SEC = 5
MAX_RECONNECT_ATTEMPTS = 20
DB_PATH = Path(__file__).parent.parent.parent / "data" / "rounds.db"


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class RoundData:
    round_id:    int
    crash:       float
    hash_:       Optional[str]
    timestamp:   float


# ─── Database Layer ───────────────────────────────────────────────────────────

class RoundDatabase:
    """SQLite persistence for resolved rounds."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS rounds (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id  INTEGER UNIQUE,
                crash     REAL NOT NULL,
                hash      TEXT,
                ts        REAL NOT NULL
            )
        """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON rounds(ts)")
        self._conn.commit()

    def insert(self, rd: RoundData) -> None:
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO rounds (round_id, crash, hash, ts) VALUES (?,?,?,?)",
                (rd.round_id, rd.crash, rd.hash_, rd.timestamp),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("DB insert failed: %s", exc)

    def fetch_recent(self, n: int = 500) -> List[Dict[str, Any]]:
        """Return the N most recent rounds as dicts, newest last."""
        cur = self._conn.execute(
            "SELECT round_id, crash, hash FROM rounds ORDER BY ts DESC LIMIT ?", (n,)
        )
        rows = cur.fetchall()
        return [{"round_id": r[0], "crash": r[1], "hash": r[2]} for r in reversed(rows)]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM rounds").fetchone()[0]


# ─── Message Parser ───────────────────────────────────────────────────────────

class RoundParser:
    """
    Parses raw WebSocket message payloads from the Aviator stream.

    The exact schema depends on the Spribe WS API version.
    This parser handles the common message format observed in traffic analysis.
    Fields are extracted defensively — missing fields produce None, not exceptions.
    """

    @staticmethod
    def parse(raw: str) -> Optional[RoundData]:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return None

        # Skip non-round messages (e.g. heartbeats, balance updates)
        msg_type = msg.get("type") or msg.get("action") or ""
        if "round" not in msg_type.lower() and "crash" not in msg_type.lower():
            return None

        data = msg.get("data") or msg

        crash_raw = (
            data.get("crashPoint")
            or data.get("crash_point")
            or data.get("multiplier")
            or data.get("crash")
        )
        if crash_raw is None:
            return None

        try:
            crash = float(crash_raw)
        except (TypeError, ValueError):
            return None

        if crash < 1.0:
            return None  # Invalid multiplier

        round_id = int(data.get("roundId") or data.get("round_id") or time.time_ns())
        hash_    = data.get("hash") or data.get("serverSeedHash") or data.get("server_seed_hash")

        return RoundData(
            round_id=round_id,
            crash=crash,
            hash_=hash_,
            timestamp=time.time(),
        )


# ─── WebSocket Listener ───────────────────────────────────────────────────────

class WebSocketListener:
    """
    Persistent async WebSocket client with exponential backoff reconnection.

    Usage:
        listener = WebSocketListener(ws_url=AVIATOR_WS_URL)
        asyncio.run(listener.start(on_round=my_callback))
    """

    def __init__(
        self,
        ws_url: str = AVIATOR_WS_URL,
        on_round: Optional[Callable[[RoundData], None]] = None,
    ) -> None:
        self.ws_url   = ws_url
        self.on_round = on_round
        self._running = False
        self._parser  = RoundParser()

    async def start(self, on_round: Optional[Callable[[RoundData], None]] = None) -> None:
        """Start the listener loop. Reconnects automatically on disconnect."""
        if on_round:
            self.on_round = on_round

        self._running = True
        attempts = 0

        while self._running and attempts < MAX_RECONNECT_ATTEMPTS:
            try:
                await self._connect()
                attempts = 0  # Reset on successful connection
            except Exception as exc:
                attempts += 1
                delay = min(RECONNECT_DELAY_SEC * (2 ** min(attempts, 6)), 120)
                logger.warning(
                    "WS connection lost (attempt %d): %s. Reconnecting in %.0fs...",
                    attempts, exc, delay,
                )
                await asyncio.sleep(delay)

        logger.info("WebSocket listener terminated.")

    def stop(self) -> None:
        self._running = False

    async def _connect(self) -> None:
        """Establish connection and stream messages."""
        try:
            import websockets
        except ImportError:
            raise RuntimeError(
                "websockets library required: pip install websockets"
            )

        logger.info("Connecting to %s", self.ws_url)
        async with websockets.connect(
            self.ws_url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            logger.info("WebSocket connected.")
            async for raw_message in ws:
                if not self._running:
                    break

                round_data = self._parser.parse(raw_message)
                if round_data:
                    logger.info(
                        "ROUND #%d | Crash: %.2fx | Hash: %s",
                        round_data.round_id,
                        round_data.crash,
                        (round_data.hash_ or "N/A")[:16],
                    )
                    if self.on_round:
                        try:
                            self.on_round(round_data)
                        except Exception:
                            logger.exception("on_round callback raised")


# ─── Data Pipeline ────────────────────────────────────────────────────────────

class DataPipeline:
    """
    Connects WebSocketListener → RoundDatabase → LivePredictor.

    This is the single entry point for running the live prediction loop.
    """

    def __init__(self, predictor=None, ws_url: str = AVIATOR_WS_URL) -> None:
        from core.engine import LivePredictor
        self._predictor = predictor or LivePredictor()
        self._db        = RoundDatabase()
        self._listener  = WebSocketListener(ws_url=ws_url)

        # Bootstrap history from DB
        stored = self._db.fetch_recent(500)
        if stored:
            self._predictor.analyzer.ingest_batch(stored)
            logger.info("Bootstrapped %d rounds from local database.", len(stored))

    def _on_round(self, rd: RoundData) -> None:
        """Callback: receive a resolved round, persist and predict."""
        self._db.insert(rd)
        self._predictor.ingest_round(rd.round_id, rd.crash, rd.hash_)

        prediction = self._predictor.predict()
        logger.info(
            "PREDICTION | safe_cashout=%.2fx | confidence=%s | patterns=%d",
            prediction.safe_cashout,
            prediction.confidence,
            len(prediction.patterns),
        )
        logger.info("RATIONALE: %s", prediction.rationale)

    async def run(self) -> None:
        """Start the full live pipeline."""
        await self._listener.start(on_round=self._on_round)

    def load_csv_history(self, csv_path: str) -> int:
        """
        Bulk-load historical round data from a CSV file for backtesting.
        CSV must have columns: round_id, crash (minimum).
        """
        import csv
        count = 0
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    rd = RoundData(
                        round_id=int(row.get("round_id", count)),
                        crash=float(row["crash"]),
                        hash_=row.get("hash"),
                        timestamp=float(row.get("timestamp", time.time())),
                    )
                    self._db.insert(rd)
                    self._predictor.ingest_round(rd.round_id, rd.crash, rd.hash_)
                    count += 1
                except (KeyError, ValueError):
                    continue
        logger.info("Loaded %d rounds from CSV: %s", count, csv_path)
        return count
