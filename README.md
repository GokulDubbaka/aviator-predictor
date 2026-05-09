# aviator-predictor — Statistical Analysis Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)](https://python.org)

A crash-game history analysis and statistics engine. Decodes provably-fair game hashes, tracks recent round history, and provides **descriptive statistics** to support informed cashout decisions.

> ⚠️ **Important disclaimer:** Crash games use provably-fair random number generation. Past patterns have **no guaranteed predictive power** over future outcomes. This tool provides statistical summaries, not predictions. Use responsibly and only where legal in your jurisdiction.

---

## Features

- **Hash Decoder** — Deterministic SHA-512 multiplier decode from a game hash
- **History Analyzer** — Rolling window statistics: percentile cashouts, streak detection, sub-2x rate
- **Pattern Detector** — Identifies streaks and distribution signals from recent history
- **Statistical Mode** — Based on resolved history; not a validated predictive model
- **Async WebSocket Listener** — Connects to live game stream for data collection

> **Note on verification:** The `verify` CLI path uses HMAC-SHA256 from raw seeds, which produces a different hash format than the SHA-512 decoder. These are two separate code paths and should not be combined.

## Quick Start

```bash
git clone https://github.com/GokulDubbaka/aviator-predictor.git
cd aviator-predictor
pip install -r requirements.txt

# Decode a known game hash
python src/cli.py decode --hash <128-char-hex>

# View statistics from collected history
python src/cli.py stats --rounds 100
```

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Test Results

`27 passed` — all 5 core layers covered.

## License

MIT — see [LICENSE](LICENSE)
