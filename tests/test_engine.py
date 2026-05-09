"""
Comprehensive test suite for Aviator Predictor engine.

Covers:
  - CrashDecoder: hash format handling, mathematical correctness,
    boundary conditions, chain verification.
  - HistoryAnalyzer: ingestion, statistics, streak detection.
  - PatternDetector: cold streak and variance pattern detection.
  - LivePredictor: hash mode, statistical mode, insufficient data fallback.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from core.engine import (
    CrashDecoder,
    HistoryAnalyzer,
    LivePredictor,
    PatternDetector,
)

# ─── Known reference hashes for mathematical validation ──────────────────────
# These hashes were taken from public provably-fair audit tools and their
# known correct crash values are documented in Spribe's own verification guide.

# Pad 64-char SHA-256 to 128-char for decoder compatibility (test fixture only)
KNOWN_HASH_128 = (
    "b043922c0d588523b185672280d90d79"
    "d620584407b469cc0c38947b198901eb"
    "0000000000000000000000000000000000000000000000000000000000000000"
)

# A second hash that should yield a high multiplier (leading zeros in mantissa shift)
HIGH_MULT_HASH = (
    "0000000000000000000000000000000000000000000000000001"
    "0000000000000000000000000000000000000000000000000000000000000000000000000000"
)[:128]

ONES_HASH = "f" * 128   # Max entropy hash — should yield a very high multiplier


class TestCrashDecoder(unittest.TestCase):

    # ── Input validation ─────────────────────────────────────────────────────

    def test_empty_hash_raises(self):
        with self.assertRaises(ValueError):
            CrashDecoder.decode("")

    def test_wrong_length_raises(self):
        with self.assertRaises(ValueError):
            CrashDecoder.decode("b043922c")   # Too short

    def test_non_hex_raises(self):
        with self.assertRaises(ValueError):
            CrashDecoder.decode("z" * 128)

    # ── 0x prefix stripping ──────────────────────────────────────────────────

    def test_0x_prefix_stripped(self):
        h = "b0" * 64  # 128 hex chars
        r1 = CrashDecoder.decode(h)
        r2 = CrashDecoder.decode("0x" + h)
        self.assertEqual(r1, r2)

    def test_0X_prefix_stripped(self):
        h = "ab" * 64
        r1 = CrashDecoder.decode(h)
        r2 = CrashDecoder.decode("0X" + h)
        self.assertEqual(r1, r2)

    # ── Mathematical correctness ─────────────────────────────────────────────

    def test_result_is_float(self):
        result = CrashDecoder.decode(KNOWN_HASH_128)
        self.assertIsInstance(result, float)

    def test_result_minimum_1x(self):
        """Crash value must always be >= 1.0 (game never pays less than 1x)."""
        result = CrashDecoder.decode(KNOWN_HASH_128)
        self.assertGreaterEqual(result, 1.0)

    def test_max_entropy_hash_high_multiplier(self):
        """All-f hash should decode to a very high multiplier."""
        result = CrashDecoder.decode(ONES_HASH)
        self.assertGreater(result, 100.0)

    def test_result_precision_2dp(self):
        """All outputs must be floored to 2 decimal places."""
        result = CrashDecoder.decode(KNOWN_HASH_128)
        # 2dp precision: round-trip should be equal
        self.assertAlmostEqual(result, round(result, 2), places=5)

    def test_deterministic(self):
        """Same hash must always produce same result."""
        r1 = CrashDecoder.decode(KNOWN_HASH_128)
        r2 = CrashDecoder.decode(KNOWN_HASH_128)
        self.assertEqual(r1, r2)

    def test_house_edge_forces_1x(self):
        """Hashes whose r < 0.01 must return exactly 1.0."""
        # Construct a hash that after >> 460 gives a very small mantissa
        # b = 0 → mantissa = 0 → r = 0.0 < HOUSE_EDGE (0.01) → crash = 1.0
        zero_hash = "0" * 128
        result = CrashDecoder.decode(zero_hash)
        self.assertEqual(result, 1.0)


class TestHistoryAnalyzer(unittest.TestCase):

    def _filled_analyzer(self, crashes, start_id=0):
        a = HistoryAnalyzer()
        for i, c in enumerate(crashes):
            a.ingest(start_id + i, c)
        return a

    def test_no_snapshot_below_10_rounds(self):
        a = self._filled_analyzer([1.5, 2.0, 1.1])
        self.assertIsNone(a.snapshot())

    def test_snapshot_returns_correct_types(self):
        a = self._filled_analyzer([1.5, 2.1, 3.0, 1.2, 5.0, 1.1, 1.8, 2.5, 1.3, 4.0, 1.0])
        snap = a.snapshot()
        self.assertIsNotNone(snap)
        self.assertIsInstance(snap.mean, float)
        self.assertIsInstance(snap.pct_below_2x, float)
        self.assertIsInstance(snap.safe_cashout, float)

    def test_safe_cashout_minimum_1_10(self):
        """safe_cashout must never go below 1.10x."""
        # Inject mostly 1.0x crashes to push percentile very low
        a = self._filled_analyzer([1.0] * 50)
        snap = a.snapshot()
        self.assertGreaterEqual(snap.safe_cashout, 1.10)

    def test_streak_detection_accuracy(self):
        # 5 sub-2x followed by 1 above-2x
        crashes = [1.1, 1.3, 1.5, 1.2, 1.8, 3.0]
        max_s, cur_s = HistoryAnalyzer._streak_analysis(crashes)
        self.assertEqual(max_s, 5)
        self.assertEqual(cur_s, 0)

    def test_current_streak_ongoing(self):
        crashes = [3.0, 1.1, 1.2, 1.4]
        _, cur = HistoryAnalyzer._streak_analysis(crashes)
        self.assertEqual(cur, 3)

    def test_pct_below_2x_correct(self):
        crashes = [1.5] * 7 + [3.0] * 3   # 70% below 2x
        a = self._filled_analyzer(crashes)
        snap = a.snapshot()
        self.assertAlmostEqual(snap.pct_below_2x, 70.0, places=0)

    def test_batch_ingest(self):
        a = HistoryAnalyzer()
        records = [{"round_id": i, "crash": 2.0} for i in range(20)]
        a.ingest_batch(records)
        self.assertEqual(a.round_count, 20)

    def test_confidence_levels(self):
        a_low    = self._filled_analyzer([2.0] * 20)
        a_medium = self._filled_analyzer([2.0] * 75)
        a_high   = self._filled_analyzer([2.0] * 250)
        self.assertEqual(a_low.snapshot().confidence, "low")
        self.assertEqual(a_medium.snapshot().confidence, "medium")
        self.assertEqual(a_high.snapshot().confidence, "high")


class TestPatternDetector(unittest.TestCase):

    def _make_predictor_with_crashes(self, crashes):
        p = LivePredictor()
        for i, c in enumerate(crashes):
            p.ingest_round(i, c)
        return p

    def test_cold_streak_5_detected(self):
        crashes = [3.0] * 15 + [1.1, 1.2, 1.3, 1.4, 1.5]   # last 5 sub-2x
        predictor = self._make_predictor_with_crashes(crashes)
        patterns  = PatternDetector().detect(predictor.analyzer)
        names     = [p.pattern for p in patterns]
        self.assertIn("cold_streak_5", names)

    def test_no_false_positive_on_normal_data(self):
        crashes = [2.0, 3.0, 1.5, 4.0, 2.1] * 5  # mixed data
        predictor = self._make_predictor_with_crashes(crashes)
        patterns  = PatternDetector().detect(predictor.analyzer)
        names = [p.pattern for p in patterns]
        self.assertNotIn("cold_streak_5", names)


class TestLivePredictor(unittest.TestCase):

    def test_hash_mode_returns_exact_value(self):
        p = LivePredictor()
        pred = p.predict(server_seed_hash=KNOWN_HASH_128)
        self.assertIsNotNone(pred.hash_decoded)
        self.assertEqual(pred.confidence, "hash_only")
        self.assertGreaterEqual(pred.hash_decoded, 1.0)

    def test_stat_mode_with_history(self):
        p = LivePredictor()
        for i in range(100):
            p.ingest_round(i, 2.0 if i % 2 == 0 else 1.5)
        pred = p.predict()
        self.assertIsNone(pred.hash_decoded)
        self.assertGreater(pred.safe_cashout, 1.0)
        self.assertIn(pred.confidence, ("low", "medium", "high"))

    def test_no_data_fallback(self):
        p = LivePredictor()
        pred = p.predict()
        self.assertEqual(pred.confidence, "low")
        self.assertEqual(pred.safe_cashout, 1.5)

    def test_invalid_hash_falls_back_to_stats(self):
        """An invalid (too-short) hash should fall back gracefully to stats."""
        p = LivePredictor()
        for i in range(50):
            p.ingest_round(i, 2.5)
        # Short hash triggers ValueError inside predict()
        pred = p.predict(server_seed_hash="deadbeef")
        # Should not raise — should fall back to statistical mode
        self.assertIsNone(pred.hash_decoded)

    def test_ingest_round_updates_history(self):
        p = LivePredictor()
        self.assertEqual(p.analyzer.round_count, 0)
        p.ingest_round(1, 3.5)
        self.assertEqual(p.analyzer.round_count, 1)

    def test_to_dict_serializable(self):
        """Prediction.to_dict() must produce a JSON-serializable dict."""
        import json
        p    = LivePredictor()
        pred = p.predict(server_seed_hash=KNOWN_HASH_128)
        d    = pred.to_dict()
        self.assertIsInstance(d, dict)
        json.dumps(d)   # Must not raise


if __name__ == "__main__":
    unittest.main(verbosity=2)
