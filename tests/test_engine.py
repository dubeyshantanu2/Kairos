from collections import deque
from kairos.engine import find_atm, evaluate
from kairos.models import PreviousDayLevels, SessionConfig

def test_find_atm_exact(make_option_row):
    chain = [
        make_option_row(21950, "CE"), make_option_row(21950, "PE"),
        make_option_row(22000, "CE"), make_option_row(22000, "PE"),
        make_option_row(22050, "CE"), make_option_row(22050, "PE"),
    ]
    atm = find_atm(chain, 22010.5, 50)
    assert atm.atm_strike == 22000
    assert atm.ce.strike == 22000
    assert atm.pe.strike == 22000

def test_evaluate_iv_cap(make_candle, make_option_row, mock_now, mock_date):
    chain = [
        make_option_row(22000, "CE", iv=0.10, gamma=0.3, theta=-0.5, oi_change=1000, ltp=150.0),
        make_option_row(22000, "PE", iv=0.10, gamma=0.3, theta=-0.5, oi_change=-500, ltp=150.0)
    ]
    c_buf = deque(maxlen=30)
    for _ in range(25):
        c_buf.append(make_candle(22000.0, volume=100, vwap=22000.0, low=21700.0, high=22300.0))
    c_buf.append(make_candle(22005.0, volume=1000, vwap=22000.0, low=21700.0, high=22300.0))
    c_buf.append(make_candle(22010.0, volume=1000, vwap=22000.0, low=21700.0, high=22300.0))
    c_buf.append(make_candle(22015.0, volume=1000, vwap=22000.0, low=21700.0, high=22300.0))
    c_buf.append(make_candle(22020.0, volume=1000, vwap=22000.0, low=21700.0, high=22300.0))
    c_buf.append(make_candle(22025.0, low=21700.0, high=22500.0, volume=1000, vwap=22000.0))
    
    i_buf = deque([0.30] * 15, maxlen=20)
    i_buf.append(0.10) # IV contracting (RED) -> triggers cap!
    
    prev = PreviousDayLevels(symbol="NIFTY", trade_date=mock_date, prev_day_high=21000, prev_day_low=20000, fetched_at=mock_now)
    config = SessionConfig(symbol="NIFTY", expiry=mock_date, expiry_type="WEEKLY", status="ACTIVE")

    score = evaluate(chain, c_buf, i_buf, prev, 22025.0, 3, config)
    assert score.iv_capped == True
    assert score.status == "CAUTION"

def test_evaluate_go_no_cap(make_candle, make_option_row, mock_now, mock_date):
    chain = [
        make_option_row(22000, "CE", iv=0.10, gamma=0.3, theta=-0.5, oi_change=1000, ltp=150.0),
        make_option_row(22000, "PE", iv=0.10, gamma=0.3, theta=-0.5, oi_change=-500, ltp=150.0)
    ]
    c_buf = deque(maxlen=30)
    for _ in range(25):
        c_buf.append(make_candle(22000.0, volume=100, vwap=22000.0, low=21700.0, high=22300.0))
    c_buf.append(make_candle(22005.0, volume=1000, vwap=22000.0, low=21700.0, high=22300.0))
    c_buf.append(make_candle(22010.0, volume=1000, vwap=22000.0, low=21700.0, high=22300.0))
    c_buf.append(make_candle(22015.0, volume=1000, vwap=22000.0, low=21700.0, high=22300.0))
    c_buf.append(make_candle(22020.0, volume=1000, vwap=22000.0, low=21700.0, high=22300.0))
    c_buf.append(make_candle(22025.0, low=21700.0, high=22500.0, volume=1000, vwap=22000.0))
    
    i_buf = deque([0.10] * 15, maxlen=20)
    i_buf.append(2.50) # +2.4 expansion => Green (2 pts)
    
    prev = PreviousDayLevels(symbol="NIFTY", trade_date=mock_date, prev_day_high=21000, prev_day_low=20000, fetched_at=mock_now)
    config = SessionConfig(symbol="NIFTY", expiry=mock_date, expiry_type="WEEKLY", status="ACTIVE")

    score = evaluate(chain, c_buf, i_buf, prev, 22025.0, 3, config)
    assert score.iv_capped == False
    assert score.score >= 7
    assert score.status == "GO"
