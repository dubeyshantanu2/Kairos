# Kairos Environment Monitor: OpenClaw Context & Integration Guide

**Target Audience:** OpenClaw Orchestrator / Gemini LLM
**Purpose:** Provide the exact technical context, architecture rules, and database schemas required for OpenClaw to operate seamlessly alongside the Python head-less scoring engine.

---

## 1. Core Architecture & OpenClaw's Role

The system is a 60-second interval condition scoring engine designed to detect favorable environments for Intraday NIFTY Options Buying.
It is **not** a signal generator. It is a live weather report pushing **🟢 GO / 🟡 CAUTION / 🔴 AVOID** alerts.

### The Boundary (Crucial Concept)
OpenClaw and the Python Engine **never communicate directly** — there are no HTTP requests or sockets between the two.
They communicate entirely via a asynchronous Shared State Bridge using **Supabase**.

```text
OpenClaw (Discord Bot)   <⇄>   Supabase (4 Tables)   <⇄>   Python Engine (VPS)
```

**OpenClaw's Responsibilities:**
1. Host Discord Slash Commands (`/start-monitor`, `/stop-monitor`).
2. Read available expiry dates from the database to present to the user.
3. Write the user's selected session configuration back to the database to start the Python scoring loop.
4. Enhance the Python engine's raw summary logs using Gemini to produce human-readable environment descriptions.

---

## 2. Interaction Flow Requirements

### Flow 1: `/start-monitor`
When the user triggers this slash command in Discord:
1. **READ:** OpenClaw queries the `available_expiries` table in Supabase.
   - The Python engine routinely populates this table with valid `symbol`, `expiry`, and `expiry_type` rows.
2. **UI:** OpenClaw displays an interactive dropdown in Discord, allowing the user to select the specific symbol (e.g., NIFTY) and expiry date.
3. **WRITE:** Once the user submits their selection, OpenClaw **MUST** write a new row to the `session_config` table:
   - `symbol` = "NIFTY"
   - `expiry` = (User selected date)
   - `expiry_type` = "WEEKLY" or "MONTHLY"
   - `status` = "ACTIVE"
4. *Effect:* Within 60 seconds, the Python Engine detects `status="ACTIVE"`, initializes its in-memory rolling buffers, fetches previous day levels, and begins scoring.

### Flow 2: `/stop-monitor`
1. **WRITE:** OpenClaw updates the `session_config` table (or inserts a new row) setting `status = "STOPPED"`.
2. *Effect:* The Python Engine detects this and halts scoring immediately.

### Flow 3: Summary Enhancement (Gemini Polishing)
The Python engine generates a compact, machine-readable string indicating the points scored across the 7 technical conditions (e.g., `iv_trend`, `momentum`, `gamma_theta`). This string is stored in `environment_log.summary_raw`.
1. **LISTEN:** OpenClaw must monitor the `environment_log` table (e.g., via Supabase Realtime subscriptions).
2. **PROCESS:** When a new state-change row appears, OpenClaw extracts `summary_raw`, passes it to Gemini to translate into a natural language sentence, and updates the `summary` column of that row.
*Note:* The Python codebase's `notifier.py` currently attempts to send Discord webhooks immediately utilizing `summary` if available, or a fallback. OpenClaw may need to either update the `summary` fast enough, edit the Discord webhook message via API after the fact, or the Python engine will need to be configured to wait for OpenClaw's update.

---

## 3. Database Schema Mapping

OpenClaw must structure its Supabase queries exactly matching these 4 tables.

### A. `session_config` (Written by OpenClaw, Read by Python)
Controls whether the Python engine is actively polling the Dhan APIs.
* **id** [SERIAL PRIMARY KEY]
* **symbol** [TEXT] -> e.g., "NIFTY"
* **expiry** [DATE] -> e.g., "2026-03-26"
* **expiry_type** [TEXT] -> "WEEKLY" or "MONTHLY"
* **status** [TEXT] -> "ACTIVE" or "STOPPED"

### B. `available_expiries` (Written by Python, Read by OpenClaw)
Used to populate the `/start-monitor` dropdown dynamically.
* **id** [SERIAL PRIMARY KEY]
* **symbol** [TEXT]
* **expiry** [DATE]
* **expiry_type** [TEXT]
* **fetched_at** [TIMESTAMPTZ] -> Used by pg_cron for cleanup

### C. `environment_log` (Written by Python, Updated by OpenClaw)
Contains the exact cycle-by-cycle scoring results. Central hub for triggering OpenClaw enhancements.
* **id** [SERIAL PRIMARY KEY]
* **timestamp** [TIMESTAMPTZ]
* **symbol** [TEXT]
* **score** [INTEGER] -> 0 to 8
* **status** [TEXT] -> "GO", "CAUTION", "AVOID"
* **iv_capped** [BOOLEAN] -> True if score was nerfed to CAUTION due to IV contraction
* **summary_raw** [TEXT] -> Python-generated machine string of condition hits
* **summary** [TEXT] -> OpenClaw/Gemini writes the polished response here

### D. `previous_day_levels` (Internal to Python)
*OpenClaw does not need to interact with this table.* Used by Python to store PDH/PDL fetched on startup to survive process restarts without redundant API calls.

---

## 4. Discord Channels & Notifications

While OpenClaw manages the conversational slash commands, **the Python engine independently utilizes Webhooks** to broadcast alerts directly to the designated Discord channels. 

1. **`#environment`**: (Powered by `discord_webhook_url`)
   - The Python engine posts state changes here (e.g., transitioning from AVOID to GO). 
   - These alerts are clean, structured grids showing condition scores mapped via emojis (🟢, 🟡, 🔴).
2. **`#system-check`**: (Powered by `discord_health_webhook_url`)
   - The Python engine will post a `💓 HEARTBEAT` every 5 minutes during active sessions.
   - It will post critical alerts, startup warm-up timers, and stale-signal warnings if the API endpoints (Dhan) fail to respond. 

OpenClaw can leverage this logic to ensure its own administrative alerts route to the same locations without muddying the clean `#environment` channel.
