"""
scheduler.py — Main entry point. Orchestrates the full system.
Manages in-memory buffers, scoring cycles, heartbeat, and health checks.
Uses APScheduler AsyncScheduler with IntervalTrigger to prevent cycle drift.
"""

import asyncio
import signal
import sys
from collections import deque
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from kairos.config import settings
from kairos.db import db
from kairos.engine import evaluate
from kairos.fetcher import DhanAPIError, DhanAuthError, fetcher
from kairos.models import PreviousDayLevels, SessionConfig
from kairos.notifier import notifier

IST = ZoneInfo("Asia/Kolkata")


# ─────────────────────────────────────────────────────────────────────────────
# Session state — shared across cycle and heartbeat jobs
# ─────────────────────────────────────────────────────────────────────────────

class SessionState:
    """Mutable session state shared between the two scheduler jobs."""

    def __init__(self) -> None:
        # In-memory rolling buffers
        self.candle_buffer: deque = deque(maxlen=settings.candle_buffer_size)
        self.iv_buffer: deque = deque(maxlen=settings.iv_buffer_size)

        # Incremental VWAP accumulators (reset each session)
        self.vwap_cumulative_volume: int = 0
        self.vwap_cumulative_num: float = 0.0

        # Session tracking
        self.active_config: Optional[SessionConfig] = None
        self.prev_levels: Optional[PreviousDayLevels] = None
        self.previous_status: Optional[str] = None

        # Health tracking
        self.cycle_count: int = 0
        self.last_fetch_time: Optional[datetime] = None
        self.last_successful_cycle_time: Optional[datetime] = None
        self.consecutive_failures: int = 0
        self.api_warning_sent: bool = False
        self.stale_alert_sent: bool = False

        # Session boundary tracking
        self.in_session: bool = False
        self.warmup_complete: bool = False
        self.startup_done: bool = False

        # API health
        self.dhan_ok: bool = True
        self.supabase_ok: bool = True

    def reset_buffers(self) -> None:
        """Reset all in-memory state when a new session starts."""
        self.candle_buffer.clear()
        self.iv_buffer.clear()
        self.vwap_cumulative_volume = 0
        self.vwap_cumulative_num = 0.0
        self.cycle_count = 0
        self.warmup_complete = False
        self.previous_status = None
        self.consecutive_failures = 0
        self.api_warning_sent = False
        self.stale_alert_sent = False
        logger.info("SessionState: buffers reset for new session")

    @property
    def warmup_cycles_remaining(self) -> int:
        """Cycles until all buffers have enough data for full scoring."""
        return max(0, settings.candle_buffer_size - len(self.candle_buffer))

    def check_warmup_complete(self) -> bool:
        """Returns True if buffers are full enough for all conditions."""
        return (
            len(self.candle_buffer) >= settings.candle_buffer_size
            and len(self.iv_buffer) >= settings.iv_change_lookback
        )


state = SessionState()


# ─────────────────────────────────────────────────────────────────────────────
# Session gate — check if within active trading hours
# ─────────────────────────────────────────────────────────────────────────────

def is_active_session() -> bool:
    """Returns True if current IST time is within an active trading session."""

    now = datetime.now(IST)
    h, m = now.hour, now.minute
    current = (h, m)

    s1_start = settings.session_1_start
    s1_end = settings.session_1_end
    s2_start = settings.session_2_start
    s2_end = settings.session_2_end

    in_s1 = s1_start <= current <= s1_end
    in_s2 = s2_start <= current <= s2_end

    return in_s1 or in_s2


def get_session_name() -> str:
    now = datetime.now(IST)
    h, m = now.hour, now.minute
    if settings.session_1_start <= (h, m) <= settings.session_1_end:
        return f"Open ({settings.session_1_start[0]:02d}:{settings.session_1_start[1]:02d}–{settings.session_1_end[0]:02d}:{settings.session_1_end[1]:02d})"
    return f"Post-Lunch ({settings.session_2_start[0]:02d}:{settings.session_2_start[1]:02d}–{settings.session_2_end[0]:02d}:{settings.session_2_end[1]:02d})"


# ─────────────────────────────────────────────────────────────────────────────
# Startup health check
# ─────────────────────────────────────────────────────────────────────────────

async def run_startup_checks(config: SessionConfig) -> bool:
    """
    Run connectivity checks and load initial data.
    Posts results to #system-check.
    Returns True if all critical checks pass.
    """
    logger.info("Running startup health checks...")

    # Test Dhan API
    try:
        state.dhan_ok = await fetcher.test_connectivity()
    except DhanAuthError:
        state.dhan_ok = False
        await notifier.post_critical_alert(
            error_type="Dhan API Auth Failed (401)",
            error_detail="Access token expired or invalid",
            last_signal_time=None,
            action_hint="Update DHAN_ACCESS_TOKEN in .env and restart service",
        )
        return False

    # Test Supabase
    state.supabase_ok = await db.test_connectivity()

    # Fetch PDH/PDL
    pdh, pdl = 0.0, 0.0
    try:
        levels = await fetcher.get_previous_day_levels(config.symbol)
        await db.write_previous_day_levels(levels)
        state.prev_levels = levels
        pdh = levels.prev_day_high
        pdl = levels.prev_day_low
        logger.info(f"PDH/PDL loaded: H={pdh} L={pdl}")
    except Exception as e:
        logger.error(f"Failed to load PDH/PDL: {e}")

    # Fetch and write available expiries for dropdown
    try:
        expiries = await fetcher.get_available_expiries(config.symbol)
        await db.write_available_expiries(expiries)
    except Exception as e:
        logger.warning(f"Failed to refresh available expiries: {e}")

    # Post startup notice
    expiry_str = f"{config.expiry.strftime('%d %b %Y')} ({config.expiry_type.title()})"
    await notifier.post_startup(
        dhan_ok=state.dhan_ok,
        supabase_ok=state.supabase_ok,
        pdh=pdh,
        pdl=pdl,
        symbol=config.symbol,
        expiry_str=expiry_str,
    )

    return state.dhan_ok


# ─────────────────────────────────────────────────────────────────────────────
# Main scoring cycle — runs every 60 seconds
# ─────────────────────────────────────────────────────────────────────────────

async def run_cycle() -> None:
    """
    One complete scoring cycle.
    Fetch → Buffer → Score → Log → Alert (if state changed)
    Uses asyncio.gather for concurrent API calls to prevent cycle drift.
    """
    # 1. Read session config
    config = await db.get_active_session()
    if config is None or config.status == "STOPPED":
        if state.in_session:
            state.in_session = False
            logger.info("Session stopped")
        return

    # First time we see an active config — run startup
    if not state.startup_done:
        state.active_config = config
        ok = await run_startup_checks(config)
        if not ok:
            return
        state.startup_done = True
        state.reset_buffers()

    # Config changed (new expiry selected) — reset buffers
    if (
        state.active_config
        and (
            state.active_config.expiry != config.expiry
            or state.active_config.symbol != config.symbol
        )
    ):
        logger.info(f"Session config changed — resetting buffers")
        state.active_config = config
        state.startup_done = False
        state.reset_buffers()
        return

    state.active_config = config

    # 2. Session gate check
    currently_in_session = is_active_session()
    if not currently_in_session:
        if state.in_session:
            state.in_session = False
            await notifier.post_session_boundary(entering=False, session_name="session")
        return

    if not state.in_session:
        state.in_session = True
        # Reset VWAP accumulators at session start
        state.vwap_cumulative_volume = 0
        state.vwap_cumulative_num = 0.0
        await notifier.post_session_boundary(
            entering=True,
            session_name=get_session_name(),
        )

    # 3. Fetch all data concurrently
    try:
        option_chain, latest_candle = await asyncio.gather(
            fetcher.get_option_chain(config.symbol, config.expiry),
            fetcher.get_latest_candle(
                config.symbol,
                cumulative_volume=state.vwap_cumulative_volume,
                cumulative_vwap_num=state.vwap_cumulative_num,
            ),
        )

        # Update VWAP accumulators
        typical_price = (latest_candle.high + latest_candle.low + latest_candle.close) / 3
        state.vwap_cumulative_volume += latest_candle.volume
        state.vwap_cumulative_num += typical_price * latest_candle.volume

        state.last_fetch_time = datetime.now(IST)
        if state.api_warning_sent:
            await notifier.post_api_recovered()
            state.api_warning_sent = False

        state.consecutive_failures = 0
        state.dhan_ok = True
        state.stale_alert_sent = False

    except DhanAuthError as e:
        state.dhan_ok = False
        state.consecutive_failures += 1
        logger.error(f"Dhan auth error: {e}")
        await notifier.post_critical_alert(
            error_type="Dhan API Auth Failed (401)",
            error_detail=str(e),
            last_signal_time=state.last_successful_cycle_time,
            action_hint="Update DHAN_ACCESS_TOKEN in .env and restart: sudo systemctl restart kairos",
        )
        return

    except DhanAPIError as e:
        state.consecutive_failures += 1
        state.dhan_ok = False
        logger.warning(f"Dhan fetch failed (attempt {state.consecutive_failures}): {e}")

        if state.consecutive_failures >= 3 and not state.api_warning_sent:
            state.api_warning_sent = True
            await notifier.post_api_warning(state.consecutive_failures, str(e))

        if state.consecutive_failures >= 5 and not state.stale_alert_sent:
            state.stale_alert_sent = True
            await notifier.post_stale_signal_warning(
                last_cycle_time=state.last_successful_cycle_time or datetime.now(IST),
                symbol=config.symbol,
            )
        return

    # 4. Guard: we need PDH/PDL
    if state.prev_levels is None:
        try:
            levels = await fetcher.get_previous_day_levels(config.symbol)
            await db.write_previous_day_levels(levels)
            state.prev_levels = levels
        except Exception as e:
            logger.error(f"Cannot score without PDH/PDL: {e}")
            return

    # 5. Update in-memory buffers
    state.candle_buffer.append(latest_candle)

    # Find ATM IV and append to iv_buffer
    interval = settings.nifty_strike_interval
    if config.symbol == "SENSEX" or config.symbol.isdigit():
        interval = settings.sensex_strike_interval

    atm_strike = round(latest_candle.close / interval) * interval
    atm_ce = next(
        (r for r in option_chain if r.strike == atm_strike and r.option_type == "CE"),
        None,
    )
    if atm_ce:
        state.iv_buffer.append(atm_ce.iv)
    else:
        logger.warning(f"ATM CE not found in option chain at strike {atm_strike}")

    state.cycle_count += 1

    # 6. Check warmup
    if not state.warmup_complete and state.check_warmup_complete():
        state.warmup_complete = True
        await notifier.post_warmup_complete(config.symbol)
        logger.info("Warmup complete — all conditions scoring normally")

    # 7. Calculate DTE
    dte = max(0, (config.expiry - date.today()).days)

    # 8. Score all 7 conditions
    try:
        score = evaluate(
            option_chain=option_chain,
            candle_buffer=state.candle_buffer,
            iv_buffer=state.iv_buffer,
            prev_levels=state.prev_levels,
            spot_price=latest_candle.close,
            dte=dte,
            session_config=config,
            previous_status=state.previous_status,
        )
    except Exception as e:
        logger.error(f"Scoring failed: {e}")
        return

    # 9. Write to Supabase
    await db.write_environment_log(score)
    state.last_successful_cycle_time = datetime.now(IST)

    # 10. State change detection and Discord alert
    if score.state_changed:
        logger.info(
            f"State change: {state.previous_status} → {score.status} "
            f"(score {score.score}/8)"
        )
        await notifier.post_environment_alert(score)

    state.previous_status = score.status
    logger.debug(
        f"Cycle {state.cycle_count}: {score.status} {score.score}/8 "
        f"(DTE={dte}, iv_capped={score.iv_capped})"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Heartbeat job — runs every 5 minutes
# ─────────────────────────────────────────────────────────────────────────────

async def run_heartbeat() -> None:
    """
    Posts a heartbeat to #system-check every 5 minutes.
    Also checks if scoring cycle has gone silent (stale signal detection).
    """
    if not state.active_config:
        return   # not started yet

    now = datetime.now(IST)

    # Check for stale signal (no successful cycle for N minutes during session)
    if (
        state.in_session
        and state.last_successful_cycle_time
        and not state.stale_alert_sent
    ):
        minutes_silent = (now - state.last_successful_cycle_time).total_seconds() / 60
        if minutes_silent >= settings.stale_signal_threshold_minutes:
            state.stale_alert_sent = True
            await notifier.post_stale_signal_warning(
                last_cycle_time=state.last_successful_cycle_time,
                symbol=state.active_config.symbol,
            )
            return

    # Post heartbeat only during or near active sessions
    expiry_str = (
        state.active_config.expiry.strftime("%d %b %Y")
        if state.active_config
        else "—"
    )

    await notifier.post_heartbeat(
        last_fetch_time=state.last_fetch_time,
        cycle_count=state.cycle_count,
        symbol=state.active_config.symbol,
        expiry_str=expiry_str,
        warmup_complete=state.warmup_complete,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    """
    Main async entry point.
    Starts all services, configures APScheduler, runs until shutdown.
    """
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}",
    )
    logger.add(
        "logs/kairos.log",
        rotation="1 day",
        retention="7 days",
        level="DEBUG",
        compression="zip",
    )

    logger.info("Kairos starting up...")

    # Start services
    await fetcher.start()
    await db.start()
    await notifier.start()

    # Graceful shutdown handler
    def handle_shutdown(sig, frame):
        logger.info(f"Received signal {sig} — shutting down")
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Start APScheduler with two independent interval jobs
    # IntervalTrigger fires on fixed intervals regardless of job duration — no drift
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_cycle,
        'interval',
        seconds=settings.poll_interval_seconds,
        id="scoring_job",
        max_instances=1,
    )
    scheduler.add_job(
        run_heartbeat,
        'interval',
        seconds=settings.heartbeat_interval_seconds,
        id="heartbeat_job",
        max_instances=1,
    )

    logger.info(
        f"Scheduler running — "
        f"scoring every {settings.poll_interval_seconds}s, "
        f"heartbeat every {settings.heartbeat_interval_seconds}s"
    )
    
    scheduler.start()

    # Run first cycle immediately on startup
    await run_cycle()

    # Keep running until interrupted
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down gracefully...")
    finally:
        scheduler.shutdown()

    # Cleanup
    await fetcher.stop()
    await db.stop()
    await notifier.stop()
    logger.info("Kairos shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
