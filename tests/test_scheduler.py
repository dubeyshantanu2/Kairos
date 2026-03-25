import pytest
import sys
from unittest.mock import MagicMock

# --- Bypass APScheduler v4 Alpha imports ---
sys.modules['apscheduler'] = MagicMock()
sys.modules['apscheduler.schedulers'] = MagicMock()
sys.modules['apscheduler.schedulers.asyncio'] = MagicMock()
sys.modules['apscheduler.triggers.interval'] = MagicMock()

from datetime import date, datetime
from collections import deque

from kairos.scheduler import run_cycle, run_heartbeat, state, is_active_session, run_startup_checks
from kairos.models import SessionConfig, OHLCVCandle, PreviousDayLevels, EnvironmentScore, OptionChainRow

@pytest.fixture
def mock_dependencies(mocker):
    # Mock all global service singletons accessed inside scheduler
    mocker.patch("kairos.scheduler.db")
    mocker.patch("kairos.scheduler.fetcher")
    mocker.patch("kairos.scheduler.notifier")
    # Patch session time check so tests do not fail organically based on clock time
    mocker.patch("kairos.scheduler.is_active_session", return_value=True)

@pytest.fixture
def dummy_session():
    return SessionConfig(
        symbol="NIFTY",
        expiry=date(2026, 3, 26),
        expiry_type="WEEKLY",
        status="ACTIVE"
    )

@pytest.fixture
def dummy_candle():
    return OHLCVCandle(
        timestamp=datetime.now(),
        symbol="NIFTY",
        interval=1,
        open=22000.0,
        high=22010.0,
        low=21990.0,
        close=22005.0,
        volume=1000,
        vwap=22000.0,
    )

@pytest.fixture
def dummy_levels():
    return PreviousDayLevels(
        symbol="NIFTY",
        trade_date=date(2026, 3, 25),
        prev_day_high=22100.0,
        prev_day_low=21900.0,
        fetched_at=datetime.now()
    )

@pytest.fixture
def dummy_score():
    return EnvironmentScore(
        timestamp=datetime.now(),
        symbol="NIFTY",
        expiry=date(2026, 3, 26),
        dte=1,
        score=8,
        max_score=8,
        status="GO",
        iv_capped=False,
        conditions=[],
        summary_raw="Raw",
        summary="Summary"
    )

from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_run_startup_checks(mock_dependencies, dummy_session, dummy_levels, mocker):
    import kairos.scheduler as sched
    
    # Setup happy path mock bounds
    sched.fetcher.test_connectivity = AsyncMock(return_value=True)
    sched.db.test_connectivity = AsyncMock(return_value=True)
    sched.fetcher.get_previous_day_levels = AsyncMock(return_value=dummy_levels)
    sched.fetcher.get_available_expiries = AsyncMock(return_value=[])
    sched.db.write_previous_day_levels = AsyncMock()
    sched.db.write_available_expiries = AsyncMock()
    sched.notifier.post_startup = AsyncMock()
    sched.notifier.post_critical_alert = AsyncMock()
    
    result = await sched.run_startup_checks(dummy_session)
    assert result is True
    assert sched.state.dhan_ok is True
    assert sched.state.supabase_ok is True

@pytest.mark.asyncio
async def test_run_cycle(mock_dependencies, dummy_session, dummy_candle, dummy_levels, dummy_score, mocker):
    import kairos.scheduler as sched
    sched.state.reset_buffers()
    sched.state.startup_done = True  # manually skip startup in basic cycle
    sched.state.in_session = True
    sched.state.prev_levels = dummy_levels
    sched.state.active_config = dummy_session
    
    sched.db.get_active_session = AsyncMock(return_value=dummy_session)
    sched.fetcher.get_option_chain = AsyncMock(return_value=[])
    sched.fetcher.get_latest_candle = AsyncMock(return_value=dummy_candle)
    sched.db.write_environment_log = AsyncMock()
    sched.notifier.post_environment_alert = AsyncMock()

    sched.notifier.post_warmup_complete = AsyncMock()
    
    # Mock evaluate to avoid deep logic requirements here
    mocker.patch("kairos.scheduler.evaluate", return_value=dummy_score)
    
    await sched.run_cycle()
    
    # Verify DB writing was invoked mapping a healthy execution frame
    sched.db.write_environment_log.assert_called_once()
    # Verify first cycle alert was sent (ADR-008)
    sched.notifier.post_environment_alert.assert_called_once()
    assert getattr(sched.state, "cycle_count") == 1

@pytest.mark.asyncio
async def test_run_heartbeat(mock_dependencies, dummy_session):
    import kairos.scheduler as sched
    sched.state.active_config = dummy_session
    sched.state.in_session = True
    
    sched.db.get_active_session = AsyncMock(return_value=dummy_session)
    sched.notifier.post_heartbeat = AsyncMock()
    sched.notifier.post_stale_signal_warning = AsyncMock()
    
    await sched.run_heartbeat()
    # Heartbeat is now suppressed per ADR-006 to reduce noise
    sched.notifier.post_heartbeat.assert_not_called()



@pytest.mark.asyncio
async def test_run_heartbeat_suppressed_when_stopped(mock_dependencies, dummy_session):
    import kairos.scheduler as sched
    from kairos.models import SessionConfig
    import datetime

    stopped_session = SessionConfig(
        symbol="NIFTY",
        expiry=datetime.date(2026, 3, 26),
        expiry_type="WEEKLY",
        status="STOPPED"
    )

    sched.db.get_active_session = AsyncMock(return_value=stopped_session)
    sched.notifier.post_heartbeat = AsyncMock()

    await sched.run_heartbeat()
    sched.notifier.post_heartbeat.assert_not_called()


@pytest.mark.asyncio
async def test_run_heartbeat_suppressed_when_no_session(mock_dependencies):
    import kairos.scheduler as sched

    sched.db.get_active_session = AsyncMock(return_value=None)
    sched.notifier.post_heartbeat = AsyncMock()

    await sched.run_heartbeat()
    sched.notifier.post_heartbeat.assert_not_called()

def test_session_helpers():
    from kairos.scheduler import is_active_session, get_session_name
    from datetime import datetime
    from zoneinfo import ZoneInfo
    ts = datetime.now(ZoneInfo("Asia/Kolkata"))
    is_active_session()
    get_session_name()

@pytest.mark.asyncio
async def test_run_startup_checks_failure(mock_dependencies, dummy_session, mocker):
    import kairos.scheduler as sched
    sched.fetcher.test_connectivity = AsyncMock(return_value=False)
    sched.db.test_connectivity = AsyncMock(return_value=False)
    sched.fetcher.get_previous_day_levels = AsyncMock(return_value=None)
    sched.notifier.post_critical_alert = AsyncMock()
    sched.notifier.post_startup = AsyncMock()
    
    result = await sched.run_startup_checks(dummy_session)
    assert result is False

@pytest.mark.asyncio
async def test_run_cycle_auth_error(mock_dependencies, dummy_session, mocker):
    import kairos.scheduler as sched
    from kairos.fetcher import DhanAuthError
    
    sched.state.reset_buffers()
    sched.state.startup_done = True
    sched.state.in_session = True
    sched.state.active_config = dummy_session
    
    sched.db.get_active_session = AsyncMock(return_value=dummy_session)
    sched.fetcher.get_latest_candle = AsyncMock()
    sched.db.write_environment_log = AsyncMock()
    sched.fetcher.get_option_chain = AsyncMock(side_effect=DhanAuthError("auth error"))
    sched.notifier.post_api_warning = AsyncMock()
    sched.notifier.post_critical_alert = AsyncMock()
    
    await sched.run_cycle()
    sched.notifier.post_critical_alert.assert_called()

@pytest.mark.asyncio
async def test_run_cycle_api_error(mock_dependencies, dummy_session, mocker):
    import kairos.scheduler as sched
    from kairos.fetcher import DhanAPIError
    
    sched.state.reset_buffers()
    sched.state.startup_done = True
    sched.state.in_session = True
    sched.state.active_config = dummy_session
    
    sched.db.get_active_session = AsyncMock(return_value=dummy_session)
    sched.fetcher.get_latest_candle = AsyncMock()
    sched.db.write_environment_log = AsyncMock()
    sched.fetcher.get_option_chain = AsyncMock(side_effect=DhanAPIError("api err"))
    sched.notifier.post_api_warning = AsyncMock()
    sched.notifier.post_critical_alert = AsyncMock()
    
    await sched.run_cycle()
    assert sched.state.consecutive_failures == 1

@pytest.mark.asyncio
async def test_run_cycle_suppressed_caution(mock_dependencies, dummy_session, dummy_candle, dummy_levels, dummy_score, mocker):
    import kairos.scheduler as sched
    sched.state.reset_buffers()
    sched.state.startup_done = True
    sched.state.in_session = True
    sched.state.prev_levels = dummy_levels
    sched.state.active_config = dummy_session
    sched.state.previous_status = "AVOID"  # Start at AVOID
    
    # Change to CAUTION (should be suppressed)
    caution_score = dummy_score.model_copy()
    caution_score.status = "CAUTION"
    caution_score.previous_status = "AVOID" # Triggers state_changed property

    
    sched.db.get_active_session = AsyncMock(return_value=dummy_session)
    sched.fetcher.get_option_chain = AsyncMock(return_value=[])
    sched.fetcher.get_latest_candle = AsyncMock(return_value=dummy_candle)
    sched.db.write_environment_log = AsyncMock()
    sched.notifier.post_environment_alert = AsyncMock()
    
    mocker.patch("kairos.scheduler.evaluate", return_value=caution_score)
    
    await sched.run_cycle()
    
    # Verify alert was NOT called for CAUTION
    sched.notifier.post_environment_alert.assert_not_called()
    assert sched.state.previous_status == "CAUTION"

@pytest.mark.asyncio
async def test_run_cycle_signal_start(mock_dependencies, dummy_session, dummy_candle, dummy_levels, dummy_score, mocker):
    """Entering GO (Signal Start) should trigger Discord alert."""
    import kairos.scheduler as sched
    sched.state.reset_buffers()
    sched.state.startup_done = True
    sched.state.in_session = True
    sched.state.prev_levels = dummy_levels
    sched.state.active_config = dummy_session
    sched.state.previous_status = "AVOID"  # Start at AVOID
    
    go_score = dummy_score.model_copy()
    go_score.status = "GO"
    go_score.previous_status = "AVOID"
    
    sched.db.get_active_session = AsyncMock(return_value=dummy_session)
    sched.fetcher.get_option_chain = AsyncMock(return_value=[])
    sched.fetcher.get_latest_candle = AsyncMock(return_value=dummy_candle)
    sched.db.write_environment_log = AsyncMock()
    sched.notifier.post_environment_alert = AsyncMock()
    
    mocker.patch("kairos.scheduler.evaluate", return_value=go_score)
    
    await sched.run_cycle()
    
    # SHOULD be called for GO
    sched.notifier.post_environment_alert.assert_called_once()
    assert sched.state.previous_status == "GO"

@pytest.mark.asyncio
async def test_run_cycle_signal_end(mock_dependencies, dummy_session, dummy_candle, dummy_levels, dummy_score, mocker):
    """Leaving GO (Signal End) should trigger Discord alert."""
    import kairos.scheduler as sched
    sched.state.reset_buffers()
    sched.state.startup_done = True
    sched.state.in_session = True
    sched.state.prev_levels = dummy_levels
    sched.state.active_config = dummy_session
    sched.state.previous_status = "GO"  # Start at GO
    
    avoid_score = dummy_score.model_copy()
    avoid_score.status = "AVOID"
    avoid_score.previous_status = "GO"
    
    sched.db.get_active_session = AsyncMock(return_value=dummy_session)
    sched.fetcher.get_option_chain = AsyncMock(return_value=[])
    sched.fetcher.get_latest_candle = AsyncMock(return_value=dummy_candle)
    sched.db.write_environment_log = AsyncMock()
    sched.notifier.post_environment_alert = AsyncMock()
    
    mocker.patch("kairos.scheduler.evaluate", return_value=avoid_score)
    
    await sched.run_cycle()
    
    # SHOULD be called when leaving GO
    sched.notifier.post_environment_alert.assert_called_once()
    assert sched.state.previous_status == "AVOID"

@pytest.mark.asyncio
async def test_run_cycle_first_alert_and_subsequent_suppression(mock_dependencies, dummy_session, dummy_candle, dummy_levels, dummy_score, mocker):
    """Verify first cycle alerts (proof of life) and subsequent suppression for same status."""
    import kairos.scheduler as sched
    sched.state.reset_buffers()
    sched.state.startup_done = True
    sched.state.in_session = True
    sched.state.prev_levels = dummy_levels
    sched.state.active_config = dummy_session
    
    sched.db.get_active_session = AsyncMock(return_value=dummy_session)
    sched.fetcher.get_option_chain = AsyncMock(return_value=[])
    sched.fetcher.get_latest_candle = AsyncMock(return_value=dummy_candle)
    sched.db.write_environment_log = AsyncMock()
    sched.notifier.post_environment_alert = AsyncMock()
    
    # 1. First cycle (AVOID) -> Should alert
    avoid_score = dummy_score.model_copy()
    avoid_score.status = "AVOID"
    mocker.patch("kairos.scheduler.evaluate", return_value=avoid_score)
    
    await sched.run_cycle()
    sched.notifier.post_environment_alert.assert_called_once()
    sched.notifier.post_environment_alert.reset_mock()
    
    # 2. Second cycle (Same status AVOID) -> Should NOT alert
    await sched.run_cycle()
    sched.notifier.post_environment_alert.assert_not_called()


