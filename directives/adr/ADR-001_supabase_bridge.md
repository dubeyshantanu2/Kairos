# ADR-001: Supabase Shared State Bridge

**Date:** 2026-03-22  
**Status:** Active  

## Problem Statement
The system consists of a Python headless scoring engine (Kairos) collecting quantitative options data, and a Discord Orchestrator (OpenClaw) providing a conversational UI for the trader. We needed a mechanism for both systems to interface—starting/stopping the engine and broadcasting the scoring sequence—without creating destructive tight-coupling or race conditions on the VPS.

## Decision Made
We opted for a **Shared State Bridge using Supabase (PostgreSQL)** instead of setting up direct Sockets or local file-reading.

### Component Boundaries & API Contracts
* **Table: `session_config`** (OpenClaw Writes -> Python Reads)
  - Python polls this lightly iteratively during `run_cycle()`. 
* **Table: `available_expiries`** (Python Writes -> OpenClaw Reads)
  - OpenClaw uses this for the Discord interface dropdown parameters.
* **Table: `environment_log`** (Python Writes -> OpenClaw Transforms)
  - Acts as the cycle ledger. Python pushes `summary_raw` here, OpenClaw translates it via Gemini to english prose prior to webhook deployment.

## Alternatives Considered
- **Direct Sockets / HTTP API:** Would require the Python engine or OpenClaw to host an active web server (e.g., FastAPI), radically complicating the deployment and introducing security vulnerabilities to the VPS' open ports.
- **Local SQLite / JSON files:** Solves the network issue but creates file-locking and immediate race conditions when simultaneously trying to serialize data. Memory corruptions would inevitably occur during high-frequency cycles.

## Performance & Security Considerations
- **Security:** Requires robust RLS (Row Level Security) policies on Supabase to prevent malicious entry. The `anon` key is strictly kept in `.env` outside of version control. 
- **Performance:** A round-trip to Supabase takes ~200ms which is completely acceptable within a 60-second execution loop. It cleanly decouples failing DB inserts from the Discord Webhook alerts via graceful `try/except` catches (meaning scoring continues even if DB drops).
