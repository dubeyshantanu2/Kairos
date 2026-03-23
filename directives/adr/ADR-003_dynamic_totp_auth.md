# ADR-003: Dynamic TOTP-Based Authentication for Dhan API

* **Task ID:** DHAN-AUTH-001
* **Date:** 2026-03-23
* **Status:** Active

## Problem Statement
Dhan API access tokens expire after 24 hours. Relying on static tokens in the `.env` file requires manual developer intervention daily to restart the VPS. This creates a single point of failure and high maintenance overhead for a 24/7 autonomous monitoring engine.

## Decision
We will transition to a **Fully Dynamic Authentication Flow** using Python's `pyotp` library.

1. **Secret Storage**: Instead of just a token, the `.env` will store the `DHAN_CLIENT_ID`, `DHAN_CLIENT_PIN`, and the `DHAN_TOTP_SECRET`.
2. **On-Demand Generation**: At startup, `DhanFetcher` will generate a fresh access token using the TOTP secret if a static token is not provided.
3. **Auto-Reauth**: The `httpx` client will trap `401 Unauthorized` responses mid-cycle, automatically trigger a TOTP-based re-authentication, and transparently retry the failed request.

## Rationale
- **Higher Availability**: The engine can now run indefinitely without manual token refreshes.
- **Improved UX**: Users of the Discord orchestrator don't need to know about "tokens" — the system manages its own session.
- **Robustness**: Handling 401s mid-flight prevents score-cycle drift and "stale data" warnings.

## Alternatives Considered
- **Static Token Script**: A separate cron job to fetch tokens. *Rejected*: Adds too many moving parts and potential race conditions with the main engine.
- **Refresh Tokens**: Dhan's API primarily uses the TOTP flow for automated systems.

## Performance & Security
- **Security**: The TOTP secret is stored as an environment variable, identical in risk level to a static token, but with the benefit of generating short-lived credentials.
- **Performance**: TOTP generation and token fetching add <500ms to a cycle, which is negligible for a 60-second loop.
