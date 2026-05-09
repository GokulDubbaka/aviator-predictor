"""
Aviator Predictor CLI — full-featured command-line interface.

Commands:
  decode  --hash <SHA512>           Deterministic decode of a single hash.
  stats   [--rounds N]              Show rolling statistics over history.
  live                              Start real-time WebSocket listener.
  load    --csv <path>              Bulk-load CSV history for analysis.
  verify  --client <seed> --server <seed> --nonce <n>  Audit a past round.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Allow running from src/ directory
sys.path.insert(0, str(Path(__file__).parent))

from core.engine import CrashDecoder, LivePredictor, HistoryAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("AviatorCLI")


# ─── Command handlers ─────────────────────────────────────────────────────────

def cmd_decode(args: argparse.Namespace) -> None:
    """Deterministically decode a SHA-512 hash into its crash multiplier."""
    try:
        crash = CrashDecoder.decode(args.hash)
        print(f"\n  Hash   : {args.hash[:24]}...{args.hash[-8:]}")
        print(f"  Crash  : {crash:.2f}x")
        print(f"  Signal : {'SAFE (>= 2x)' if crash >= 2.0 else 'CRASH (< 2x)'}\n")
    except ValueError as exc:
        logger.error("Hash decode failed: %s", exc)
        sys.exit(1)


def cmd_verify(args: argparse.Namespace) -> None:
    """Independently verify a past round using raw seeds."""
    try:
        crash = CrashDecoder.verify_chain(args.client, args.server, int(args.nonce))
        print(f"\n  Verified crash: {crash:.2f}x\n")
    except Exception as exc:
        logger.error("Verification failed: %s", exc)
        sys.exit(1)


def cmd_stats(args: argparse.Namespace) -> None:
    """Print statistical analysis over loaded history."""
    predictor = LivePredictor()

    # Attempt to bootstrap from local DB
    try:
        from core.ingestion import RoundDatabase
        db      = RoundDatabase()
        records = db.fetch_recent(args.rounds)
        if records:
            predictor.analyzer.ingest_batch(records)
            logger.info("Loaded %d rounds from local database.", len(records))
        else:
            logger.warning("No rounds in local database. Use 'load --csv' first.")
    except Exception as exc:
        logger.warning("Could not load DB: %s", exc)

    prediction = predictor.predict()
    snap       = prediction.stat_snapshot

    print("\n" + "=" * 55)
    print("  AVIATOR STATISTICAL ANALYSIS")
    print("=" * 55)

    if snap:
        print(f"  Rounds analyzed  : {snap.count}")
        print(f"  Mean crash       : {snap.mean:.3f}x")
        print(f"  Median crash     : {snap.median:.3f}x")
        print(f"  Std deviation    : {snap.std_dev:.3f}")
        print(f"  Sub-2x rate      : {snap.pct_below_2x:.1f}%")
        print(f"  Sub-1.5x rate    : {snap.pct_below_1_5x:.1f}%")
        print(f"  Above-10x rate   : {snap.pct_above_10x:.1f}%")
        print(f"  Current sub-2x   : {snap.current_streak_below_2x} consecutive")
        print(f"  Max sub-2x streak: {snap.max_streak_below_2x}")
        print(f"  Safe cashout     : {snap.safe_cashout:.2f}x ({snap.confidence} confidence)")
    else:
        print("  Insufficient data for statistics.")

    if prediction.patterns:
        print("\n  PATTERNS DETECTED:")
        for p in prediction.patterns:
            print(f"    [{p.strength*100:.0f}%] {p.pattern}: {p.implication}")

    print(f"\n  RATIONALE: {prediction.rationale}")
    print("=" * 55 + "\n")


def cmd_live(args: argparse.Namespace) -> None:
    """Start the real-time WebSocket pipeline."""
    from core.ingestion import DataPipeline

    logger.info("Starting live pipeline. Press Ctrl+C to stop.")
    pipeline = DataPipeline()

    try:
        asyncio.run(pipeline.run())
    except KeyboardInterrupt:
        logger.info("Live pipeline stopped by user.")


def cmd_load(args: argparse.Namespace) -> None:
    """Bulk-load a CSV file of historical rounds."""
    from core.ingestion import DataPipeline

    pipeline = DataPipeline()
    n = pipeline.load_csv_history(args.csv)
    print(f"\n  Loaded {n} rounds from {args.csv}")
    print("  Run 'stats' to analyze.\n")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="aviator",
        description="Aviator Crash Multiplier Predictor",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # decode
    p_decode = sub.add_parser("decode", help="Decode a SHA-512 hash into crash multiplier")
    p_decode.add_argument("--hash", required=True, help="128-char SHA-512 hex hash")

    # verify
    p_verify = sub.add_parser("verify", help="Verify a past round from raw seeds")
    p_verify.add_argument("--client", required=True, help="Client seed string")
    p_verify.add_argument("--server", required=True, help="Server seed string (post-round reveal)")
    p_verify.add_argument("--nonce",  required=True, help="Round nonce integer")

    # stats
    p_stats = sub.add_parser("stats", help="Statistical analysis over history")
    p_stats.add_argument("--rounds", type=int, default=500, help="Max rounds to analyze (default: 500)")

    # live
    sub.add_parser("live", help="Start real-time WebSocket listener")

    # load
    p_load = sub.add_parser("load", help="Bulk-load CSV history")
    p_load.add_argument("--csv", required=True, help="Path to CSV file (columns: round_id, crash, hash)")

    args = parser.parse_args()

    dispatch = {
        "decode": cmd_decode,
        "verify": cmd_verify,
        "stats":  cmd_stats,
        "live":   cmd_live,
        "load":   cmd_load,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
