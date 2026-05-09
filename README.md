# ✈️ Aviator Analyser — Statistical History Tool

> **Status:** Working CLI · Research/educational use only · NOT a predictor

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org)

---

## ⚠️ CRITICAL DISCLAIMER — READ FIRST

```
════════════════════════════════════════════════════════════
  STATISTICAL ANALYSIS — Not a Predictor
  
  The Aviator crash game uses a Provably Fair RNG (Random
  Number Generator) cryptographically seeded per round.
  Past multipliers have ZERO predictive power over future
  results. No pattern, model, or algorithm can predict the
  next crash point.
  
  This tool analyses HISTORICAL data only — like studying
  coin flip statistics. It cannot tell you when to cash out.
  
  Using this tool for gambling decisions will result in
  financial loss. Gambling carries serious financial risk.
════════════════════════════════════════════════════════════
```

---

## 🎯 What This Is

A **purely analytical CLI tool** for researchers studying the statistical properties of Aviator game history data. Think of it like studying coin-flip distributions — interesting mathematically, but incapable of predicting the next flip.

**Academic use cases:**
- Verifying the provably fair RNG behaves as expected (uniform distribution)
- Studying streak lengths and multiplier frequency distributions
- Understanding why gambler's fallacy is dangerous in provably fair games

---

## ✅ What Actually Works

```bash
pip install -r requirements.txt
python src/cli.py stats --rounds 1000
python src/cli.py stats --min 2.0          # Filter rounds ≥ 2x multiplier
python src/cli.py ingest --file history.csv
python src/cli.py stats --export report.json
```

- Statistical summary: mean, median, standard deviation, percentiles
- Streak analysis: consecutive sub-2x runs, max multiplier sequences
- Distribution bucketing: frequency counts per multiplier range
- CSV ingestion of exported game history

---

## ❌ What We Have NOT Achieved (And Cannot Achieve)

| Claim | Reality |
|-------|---------|
| "Predict next crash point" | **Mathematically impossible** — provably fair RNG means each round is independent |
| "Find patterns that repeat" | **Gambler's fallacy** — past results carry zero information about future |
| "Safe strategy for cashing out" | **Does not exist** — house edge is built into the RNG distribution |
| "Beat the house with statistics" | **False** — statistics confirms the house edge, it does not remove it |

**Why we built it anyway:** Understanding *why* prediction is impossible is valuable. This tool proves it empirically — the distribution matches theoretical RNG expectations, confirming no exploitable pattern exists.

---

## 🤝 How You Can Help

- **RNG verification:** Implement the provably fair hash verification algorithm so users can audit individual rounds against the server seed
- **Visualisation:** Add matplotlib/plotly charts of multiplier distributions
- **Export formats:** PDF statistical reports for academic use
- **Data ingestion:** Support more game platforms' CSV export formats

---

## 📄 License

MIT — see [LICENSE](LICENSE)
