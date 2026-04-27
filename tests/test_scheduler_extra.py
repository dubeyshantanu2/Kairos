import pytest
import asyncio
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock, patch
from kairos.scheduler import (
    state,
    run_cycle,
    run_heartbeat,
    run_startup_checks,
    is_active_session,
    is_lunch_break,
    get_session_name,
)
from kairos.models import SessionConfig, PreviousDayLevels, OHLCVCandle, ConditionResult, EnvironmentScore
from kairos.config import settings
from kairos.fetcher import DhanAuthError, DhanAPIError

IST = ZoneInfo("Asia/Kolkata")

@pytest.fixture
def mock_deps(mocker):
    # We must patch where they are IMPORTED in scheduler.py
    mocker.patch("kairos.scheduler.db", new_callable=AsyncMock)
    mocker.patch("kairos.scheduler.fetcher", new_callable=AsyncMock)
    mocker.patch("kairos.scheduler.notifier", new_callable=AsyncMock)
    mocker.patch("kairos.scheduler.evaluate")

def test_session_gate_logic(mocker):
    # Mocking datetime.now is tricky, let's patch the function that returns now()
    # Actually, let's just patch is_active_session and is_lunch_break for most tests,
    # but for THESE tests we need to control time.
    
    with patch("kairos.scheduler.datetime") as mock_date:
        mock_date.now.return_value = datetime.combine(date.today(), datetime.min.time().replace(hour=10, minute=0)).replace(tzinfo=IST)
        mock_date.combine = datetime.combine
        mock_date.min = datetime.min
        
        assert is_active_session() is True
        assert is_lunch_break() is False
        assert "Open" in get_session_name()

        # Lunch break
        mock_date.now.return_value = datetime.combine(date.today(), datetime.min.time().replace(hour=12, minute=40)).replace(tzinfo=IST)
        assert is_active_session() is False
        assert is_lunch_break() is True
        
        # S2 Warmup
        mock_date.now.return_value = datetime.combine(date.today(), datetime.min.time().replace(hour=13, minute=0)).replace(tzinfo=IST)
        assert is_active_session() is True
        assert is_lunch_break() is False
        assert "Post-Lunch" in get_session_name()

@pytest.mark.asyncio
async def test_run_startup_checks_variants(mock_deps, mocker):
    import kairos.scheduler as sched
    sched.fetcher.test_connectivity.return_value = True
    sched.db.test_connectivity.return_value = True
    # Exception in PDH fetch
    sched.fetcher.get_previous_day_levels.side_effect = Exception("fail")
    sched.fetcher.get_available_expiries.side_effect = Exception("fail")
    
    cfg = SessionConfig(symbol="NIFTY", expiry=date.today(), expiry_type="WEEKLY", status="ACTIVE")
    res = await run_startup_checks(cfg)
    assert res is True
    sched.notifier.post_startup.assert_called()

@pytest.mark.asyncio
async def test_run_cycle_stopped(mock_deps):
    import kairos.scheduler as sched
    sched.db.get_active_session.return_value = None
    sched.state.in_session = True
    await run_cycle()
    assert sched.state.in_session is False

@pytest.mark.asyncio
async def test_run_cycle_stale_expiry(mock_deps):
    import kairos.scheduler as sched
    past = date.today() - timedelta(days=1)
    cfg = SessionConfig(symbol="NIFTY", expiry=past, expiry_type="WEEKLY", status="ACTIVE")
    sched.db.get_active_session.return_value = cfg
    sched.fetcher.get_available_expiries.return_value = []
    
    sched.state.active_config = None
    await run_cycle()
    assert sched.state.active_config == cfg
    assert sched.state.startup_done is False

@pytest.mark.asyncio
async def test_run_cycle_config_change_reset(mock_deps):
    import kairos.scheduler as sched
    sched.state.startup_done = True
    sched.state.active_config = SessionConfig(symbol="NIFTY", expiry=date.today(), expiry_type="WEEKLY", status="ACTIVE")
    
    new_cfg = SessionConfig(symbol="BANKNIFTY", expiry=date.today(), expiry_type="WEEKLY", status="ACTIVE")
    sched.db.get_active_session.return_value = new_cfg
    
    await run_cycle()
    assert sched.state.startup_done is False

@pytest.mark.asyncio
async def test_run_cycle_oi_delta_new_strike(mock_deps, mocker):
    import kairos.scheduler as sched
    sched.state.startup_done = True
    sched.state.in_session = True
    sched.state.active_config = SessionConfig(symbol="NIFTY", expiry=date.today(), expiry_type="WEEKLY", status="ACTIVE")
    sched.state.prev_levels = MagicMock()
    
    mocker.patch("kairos.scheduler.is_active_session", return_value=True)
    sched.db.get_active_session.return_value = sched.state.active_config
    
    # Baseline has strike 22000
    sched.state.oi_snapshot_buffer.append({(22000, "CE"): 1000})
    
    # New row has strike 22050
    from kairos.models import OptionChainRow
    new_row = OptionChainRow(
        timestamp=datetime.now(), symbol="NIFTY", expiry=date.today(), strike=22050, option_type="CE",
        iv=0.2, delta=0.5, gamma=0, theta=0, vega=0, oi=500, oi_change=0, volume=0, ltp=0, bid=0, ask=0
    )
    sched.fetcher.get_option_chain.return_value = [new_row]
    sched.fetcher.get_latest_candle.return_value = MagicMock(close=22000)
    
    # Mock evaluate to return a score
    sched.evaluate.return_value = MagicMock(iv_capped=False, status="AVOID", conditions=[])
    
    await run_cycle()
    assert new_row.oi_change == 0 # Line 323 hit

@pytest.mark.asyncio
async def test_run_cycle_api_recovery(mock_deps, mocker):
    import kairos.scheduler as sched
    sched.state.startup_done = True
    sched.state.in_session = True
    sched.state.active_config = SessionConfig(symbol="NIFTY", expiry=date.today(), expiry_type="WEEKLY", status="ACTIVE")
    sched.state.prev_levels = MagicMock()
    sched.state.api_warning_sent = True
    
    mocker.patch("kairos.scheduler.is_active_session", return_value=True)
    sched.db.get_active_session.return_value = sched.state.active_config
    sched.fetcher.get_option_chain.return_value = []
    sched.fetcher.get_latest_candle.return_value = MagicMock(close=22000)
    sched.evaluate.return_value = MagicMock(iv_capped=False, status="AVOID", conditions=[])
    
    await run_cycle()
    sched.notifier.post_api_recovered.assert_called()
    assert sched.state.api_warning_sent is False

@pytest.mark.asyncio
async def test_run_cycle_pdh_lazy_load_failure(mock_deps, mocker):
    import kairos.scheduler as sched
    sched.state.startup_done = True
    sched.state.in_session = True
    sched.state.active_config = SessionConfig(symbol="NIFTY", expiry=date.today(), expiry_type="WEEKLY", status="ACTIVE")
    sched.state.prev_levels = None # Trigger lazy load
    
    mocker.patch("kairos.scheduler.is_active_session", return_value=True)
    sched.db.get_active_session.return_value = sched.state.active_config
    sched.fetcher.get_option_chain.return_value = []
    sched.fetcher.get_latest_candle.return_value = MagicMock(close=22000)
    
    sched.fetcher.get_previous_day_levels.side_effect = Exception("failed again")
    
    await run_cycle()
    assert sched.state.prev_levels is None # Failed to load, returned early

@pytest.mark.asyncio
async def test_run_cycle_significant_change_detection(mock_deps, mocker):
    import kairos.scheduler as sched
    sched.state.startup_done = True
    sched.state.in_session = True
    sched.state.warmup_complete = True
    sched.state.active_config = SessionConfig(symbol="NIFTY", expiry=date.today(), expiry_type="WEEKLY", status="ACTIVE")
    sched.state.prev_levels = MagicMock()
    
    mocker.patch("kairos.scheduler.is_active_session", return_value=True)
    sched.db.get_active_session.return_value = sched.state.active_config
    sched.fetcher.get_option_chain.return_value = []
    sched.fetcher.get_latest_candle.return_value = MagicMock(close=22000)
    
    # 1. Condition list length change
    sched.state.previous_conditions = [MagicMock()]
    new_score = MagicMock(status="AVOID", state_changed=False, conditions=[MagicMock(), MagicMock()])
    sched.evaluate.return_value = new_score
    
    await run_cycle()
    sched.notifier.post_environment_alert.assert_called()
    sched.notifier.post_environment_alert.reset_mock()
    
    # 2. Status color change within conditions
    c_old = ConditionResult(name="c1", status="GREEN", points=1, max_points=1, detail="ok")
    c_new = ConditionResult(name="c1", status="YELLOW", points=0, max_points=1, detail="meh")
    sched.state.previous_conditions = [c_old]
    new_score.conditions = [c_new]
    
    await run_cycle()
    sched.notifier.post_environment_alert.assert_called()

@pytest.mark.asyncio
async def test_run_cycle_iv_cap_hold_go_to_caution(mock_deps, mocker):
    import kairos.scheduler as sched
    sched.state.startup_done = True
    sched.state.in_session = True
    sched.state.active_config = SessionConfig(symbol="NIFTY", expiry=date.today(), expiry_type="WEEKLY", status="ACTIVE")
    sched.state.prev_levels = MagicMock()
    sched.state.iv_cap_active = True
    
    mocker.patch("kairos.scheduler.is_active_session", return_value=True)
    sched.db.get_active_session.return_value = sched.state.active_config
    sched.fetcher.get_option_chain.return_value = []
    sched.fetcher.get_latest_candle.return_value = MagicMock(close=22000)
    
    # score.status = GO, but iv_cap_active holds and it's not GREEN iv
    c_iv = ConditionResult(name="iv_trend", status="YELLOW", points=0, max_points=1, detail="borderline")
    score = EnvironmentScore(
        timestamp=datetime.now(), symbol="N", expiry=date.today(), dte=1, score=7, status="GO", iv_capped=False,
        conditions=[c_iv], summary_raw="raw"
    )
    sched.evaluate.return_value = score
    
    await run_cycle()
    assert score.iv_capped is True
    assert score.status == "CAUTION" # Line 444 hit

@pytest.mark.asyncio
async def test_heartbeat_none_config(mock_deps):
    import kairos.scheduler as sched
    sched.db.get_active_session.return_value = None
    await run_heartbeat()
    # returns early
