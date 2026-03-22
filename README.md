# Kairos — NIFTY Options Scalping Environment Monitor

A real-time environment monitor for intraday NIFTY options buying.
Scores 7 market conditions every minute and posts 🟢 GO / 🟡 CAUTION / 🔴 AVOID
alerts to Discord via OpenClaw.

---

## Project Structure

```
src/kairos/
├── config.py       All settings and thresholds (single source of truth)
├── models.py       Pydantic data models
├── fetcher.py      Dhan API integration
├── processor.py    7 condition scoring functions
├── engine.py       Score aggregation, IV cap, DTE scaling
├── db.py           Supabase client (4 tables only)
├── notifier.py     Discord webhook poster
└── scheduler.py    Main entry point — scoring loop + heartbeat
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/your-repo/kairos.git
cd kairos
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your actual credentials
```

### 3. Set up Supabase

Run `supabase_schema.sql` in your Supabase SQL Editor.
This creates all 4 tables, indexes, and pg_cron cleanup jobs.

### 4. Run locally (development)

```bash
python -m kairos.scheduler
```

---

## VPS Deployment

### 1. Create system user

```bash
sudo useradd -m -s /bin/bash kairos
sudo su - kairos
```

### 2. Clone and set up

```bash
git clone https://github.com/your-repo/kairos.git
cd kairos
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# Edit .env with production credentials
```

### 3. Install systemd service

```bash
sudo cp kairos.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kairos
sudo systemctl start kairos
```

### 4. Monitor

```bash
# Live logs
journalctl -u kairos -f

# Status
sudo systemctl status kairos

# Restart after code update
cd /home/kairos/kairos && git pull
sudo systemctl restart kairos
```

---

## Discord Commands (via OpenClaw)

| Command | Action |
|---------|--------|
| `/start-monitor` | Select symbol + expiry, start monitoring |
| `/stop-monitor` | Stop monitoring |

### Channels

| Channel | Purpose |
|---------|---------|
| `#environment` | GO / CAUTION / AVOID alerts (state change only) |
| `#system-check` | Heartbeat, startup, errors, stale signal warnings |

---

## Scoring

| Condition | Weight | Max Points |
|-----------|--------|-----------|
| IV Change Rate | 2x | 2 |
| Momentum + Trend | 1x | 1 |
| OI Flow | 1x | 1 |
| Gamma/Theta (DTE-scaled) | 1x | 1 |
| PDH/PDL Breakout | 1x | 1 |
| Move Ratio (30-min) | 1x | 1 |
| VWAP Distance | 1x | 1 |
| **Total** | | **8** |

| Score | Status |
|-------|--------|
| 7–8 | 🟢 GO |
| 4–6 | 🟡 CAUTION |
| 0–3 | 🔴 AVOID |

**IV Contraction Cap:** If IV is contracting (🔴), maximum output is capped
at CAUTION regardless of other conditions.

---

## Extending to SENSEX (Phase 2)

1. Update `session_config` to support SENSEX symbol
2. Change `fetcher.py` `security_id` mapping for SENSEX (BSE scrip code)
3. All scoring logic works as-is — `strike_interval` auto-selects 100 for SENSEX
