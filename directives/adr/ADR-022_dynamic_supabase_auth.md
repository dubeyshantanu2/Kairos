# ADR-022: Dynamic Supabase Bridge Authentication & Recovery

* **Task ID:** DHAN-AUTH-002
* **Date:** 2026-06-19
* **Status:** Active

## Problem Statement
Dhan API access tokens expire after 24 hours. Under the previous TOTP-based authentication architecture (ADR-003), multiple running instances of ARES or related cron microservices generating tokens independently invalidated each other's active sessions (Dhan's backend only allows one active token per user account). This tight coupling also meant local developers and scaled VPS machines required sensitive TOTP seeds and login PINs in their local `.env` files.

## Decision
We will transition to a **Single-Writer / Multi-Reader Shared State Bridge** pattern for authentication, leveraging our existing Supabase cluster:

1. **Centralized Token Renewal**: A centralized microservice (running as a FastAPI web server on Fly.io) handles the actual token renewal process on a periodic cron schedule and writes the active `client_id` and `access_token` to the `api_keys` table in Supabase.
2. **Startup Retrieval**: At startup, ARES retrieves the active credentials from Supabase, dynamically populating the unified `Settings` wrapper before initializing any API clients.
3. **Mid-Session Recovery**: If the engine catches an authentication error (e.g., `401 Unauthorized` or exception containing `auth` or `401`), it halts, re-queries the Supabase `api_keys` table for the fresh token renewed by the centralized daemon, re-initializes the `DhanFetcher` client context, and retries the cycle.
4. **Local Secret Removal**: Remove `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN`, `DHAN_CLIENT_PIN`, and `DHAN_TOTP_SECRET` entirely from local `.env` and `.env.example` configurations.

## Rationale
- **Zero Token Conflicts**: By routing all token generation through a single centralized daemon, we ensure ARES readers never generate conflicting tokens.
- **Enhanced Security**: Local configurations and deployments no longer house active API tokens, login PINs, or raw 2FA TOTP secrets.
- **Resilience**: ARES is completely self-healing mid-session. If a token expires or is invalidated, it is refreshed silently from the database without system alerts or crash restarts.

## Alternatives Considered
- **Distributed TOTP Synchronization**: Syncing TOTP triggers across VPS machines. *Rejected*: Highly complex and error-prone due to clock drift and timing overlaps.

## Performance & Security
- **Performance**: Retries only trigger on a `401` error. A database query on startup adds a tiny one-time ~200ms latency which is negligible.
- **Database Schema**: Leverages `public.api_keys` with columns `provider` (PK), `client_id`, and `access_token`.
