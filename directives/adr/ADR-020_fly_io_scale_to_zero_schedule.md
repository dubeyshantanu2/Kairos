# ADR-020 Fly.io Scale-to-Zero and Automatic Shutdown
**Date:** 2026-04-27
**Status:** Active

## Context
The Kairos Python Engine operates strictly during Indian Standard Time (IST) market hours (09:15 to 15:30). Running the engine 24/7 on Fly.io incurs unnecessary compute costs since the Indian markets are closed for ~18 hours a day, including weekends. We needed an automated way to scale the application infrastructure according to market sessions.

## Decision
We implemented a two-part scale-to-zero strategy:

1. **Application-Level Automatic Shutdown:**
   - Modified `src/kairos/config.py` to slightly extend the defined `session_2_end` to `15:25` IST, ensuring all closing activities (like posting the session boundary message to Discord) complete safely without abruptly cutting off at exactly `15:15` or `15:30`.
   - Modified `src/kairos/scheduler.py`'s `run_cycle` to verify the current time against `session_2_end`. Unconditionally call `sys.exit(0)` if the time has passed the end of the trading day.
   - When the process exits with `sys.exit(0)`, the Fly.io Machine effectively shuts down if the process is the primary one, moving from `started` to `stopped` state.

2. **Infrastructure-Level Scheduling via GitHub Actions:**
   - Created a `.github/workflows/market-hours.yml` workflow relying on cron triggers.
   - Using `flyctl scale count`, the workflow provisions `1` machine shortly before market open (09:15 IST) and scales down to `0` machines well after market close (15:25 IST) on weekdays (Mon-Fri).
   - This ensures the compute container is only active when required and completely destroyed outside market hours to save costs.

## Rationale
Fly.io supports auto-start/auto-stop primarily for HTTP applications via its proxy mechanism. Since Kairos is a background worker (no HTTP traffic, just an autonomous polling loop reporting outbound to Discord), it cannot be natively scaled to zero via HTTP wake-ups. 

By having the process gracefully terminate itself post-market and utilizing GitHub Actions cron triggers to instruct the Fly.io API to provision compute, we achieve highly predictable and robust infrastructure scaling explicitly decoupled from complex auto-scaling mechanisms.

## Alternatives Considered
- Writing a custom HTTP wrapper simply to trigger Fly.io's auto-wake-up proxy. Rejected as it adds artificial overhead to the architectural pattern.
- Using Fly.io's built in `schedule` in `fly.toml`. Currently not feature-rich enough or reliable for exact start/stop timings mapping to IST.

## Consequences
- The Github Action explicitly requires a `FLY_API_TOKEN` Github secret.
- Local execution is also affected: leaving the scheduler running locally after hours will safely shut it down.
