# Kairos: Scalping Environment Monitor

An intraday condition scoring engine designed specifically for **NIFTY Options Buying**. 

It does **not** generate trade signals. Instead, it acts as a live weather report, aggregating complex market data (Momentum, IV Flow, Gammas, VWAP) into a simple broadcast alert: **🟢 GO**, **🟡 CAUTION**, or **🔴 AVOID**.

---

## 📈 Market Trend Phases

Kairos implements a 5-phase trend classification system that correlates relative price change with At-The-Money (ATM) Open Interest flow over a 5-minute rolling window. This provides deeper context beyond just "Bullish" or "Bearish" conviction.

| Phase | Price Δ | OI Δ | Interpretation |
|---|---|---|---|
| **Long Buildup 🟢** | Positive | Positive | Fresh buying; strong bullish conviction. |
| **Short Covering 🔵** | Positive | Negative | Sellers exiting; technical rally/bounce. |
| **Short Buildup 🔴** | Negative | Positive | Fresh selling; strong bearish conviction. |
| **Long Unwinding 🟠**| Negative | Negative | Buyers exiting; profit booking or capitulation. |
| **Neutral 🟡** | Varied | < Threshold | Consolidation or low participation. |

*Note: The default threshold is set to 5,000 ATM OI (CE+PE) as defined in `config.py`.*

---

## 🏗 System Architecture

The trading environment is entirely orchestrated through Discord via the Discord orchestrator bot. The Python Engine (this repository) runs headlessly on a VPS and communicates exclusively through an asynchronous **Supabase Shared State Bridge**.

```mermaid
graph TD
    %% Entities
    User((Trader))
    Discord[Discord App]
    Orchestrator[Discord Orchestrator\nBot]
    Supabase[(Supabase\nPostgreSQL)]
    Kairos[Kairos Python Engine\nVPS Headless]
    Dhan[Dhan API]
    
    %% Flows
    User -->|/start-monitor| Discord
    Discord --> Orchestrator
    Orchestrator -->|Writes session_config| Supabase
    
    Kairos -->|Reads session_config| Supabase
    Kairos -->|Polls live market data| Dhan
    
    Kairos -->|Calculates 7 Conditions\nWrites summary_raw| Supabase
    Orchestrator -->|Transforms summary via Gemini| Supabase
    
    Kairos -->|State changed?\nBroadcast Alert Wehbook| Discord
    Discord -->|#environment /\n#system-check| User
```

---

## 📚 Advanced Documentation

If you are expanding this repository or integrating the orchestrator, please review the core documentation files before modifying logic:

- **[Discord Bot Integration Guide](docs/integration.md):** Exact responsibilities and database map for the Discord Bot side.
- **[Mathematical Scoring Architecture](docs/scoring_architecture.md):** The absolute source-of-truth for the 7 scoring condition parameters, lookback windows, and IV Cap logic.
- **[Architecture Decision Records (ADRs)](directives/adr/INDEX.md):** The historical log of system design choices, including why Supabase was chosen over WebSockets.
- **[Changelog](CHANGELOG.md):** Build milestones and test suite updates.

---

## 🛠 Developer Setup

If you are running the Kairos engine locally for development or testing:

### 1. Installation
This repository uses `pyproject.toml` standards. Ensure you have Python 3.10+ installed.
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Environment Variables
Copy the `.env.example` to `.env` and fill out your local secrets. 
**Note:** `.env` is explicitly ignored by `git`. Never commit your Dhan tokens or Supabase keys.

| Variable | Description |
|---|---|
| `DHAN_CLIENT_ID` | Your Dhan HQ Client ID. |
| `DHAN_ACCESS_TOKEN` | (Optional) Dhan HQ Access Token. If provided, TOTP is bypassed. |
| `DHAN_CLIENT_PIN` | (Required for TOTP) 4-digit Dhan login PIN. |
| `DHAN_TOTP_SECRET` | (Required for TOTP) The 32-character seed (Key) from Dhan's 2FA setup. |
| `SUPABASE_URL` | Your Supabase project URL (`https://xyz.supabase.co`). |
| `SUPABASE_KEY` | Public `anon` API key for Supabase restricted via RLS. |
| `DISCORD_WEBHOOK_URL` | Webhook URL for the `#environment` channel. |
| `DISCORD_HEALTH_WEBHOOK_URL`| Webhook URL for the `#system-check` channel. |
| `OI_LOOKBACK_CYCLES` | (Optional) Num cycles for OI delta calculation (default: 5). |

### 3. Running the Test Suite
The codebase includes an exhaustive `pytest` suite ensuring all mathematical thresholds map to the correct 🟢/🟡/🔴 point system.
```bash
python -m pytest tests/ -v
```

### 4. Running the Engine
```bash
python -m kairos.scheduler
```
*(Ensure a valid session is marked as `ACTIVE` inside your Supabase `session_config` table, otherwise the engine will gracefully idle.)*

### 5. Direct CLI Control (Bypass Discord)
For development or manual testing, you can control the monitoring session directly from the terminal without using the Discord Bot.
```bash
# Start monitoring NIFTY for a specific expiry
python execution/control_panel.py start NIFTY 2026-04-16 --type WEEKLY

# Stop the active session
python execution/control_panel.py stop
```
