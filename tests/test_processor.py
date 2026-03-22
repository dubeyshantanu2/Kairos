from collections import deque
from kairos.processor import (
    score_iv_change,
    score_momentum,
    score_oi_flow,
    score_gamma_theta,
    score_pdhl_breakout,
    score_move_ratio,
    score_vwap_distance,
)
from kairos.models import PreviousDayLevels

def test_score_iv_change_warmup():
    buf = deque([0.15] * 10, maxlen=20)
    res = score_iv_change(buf)
    assert res.status == "YELLOW"
    assert "Warming up" in res.detail

def test_score_iv_change_green():
    buf = deque([0.15] * 15, maxlen=20)
    buf.append(1.8) # 1.8 - 0.15 = 1.65 > 1.5
    res = score_iv_change(buf)
    assert res.status == "GREEN"
    assert res.points == 2

def test_score_iv_change_yellow():
    buf = deque([0.15] * 15, maxlen=20)
    buf.append(0.5) # 0.5 - 0.15 = 0.35 > 0.0
    res = score_iv_change(buf)
    assert res.status == "YELLOW"
    assert res.points == 1

def test_score_iv_change_red():
    buf = deque([0.15] * 15, maxlen=20)
    buf.append(0.10) # 0.10 - 0.15 = -0.05 < 0.0
    res = score_iv_change(buf)
    assert res.status == "RED"
    assert res.points == 0

def test_score_momentum_green(make_candle):
    buf = deque(maxlen=20)
    for _ in range(15):
        buf.append(make_candle(100.0, volume=100))
    # 5 recent candles trending up
    buf.append(make_candle(100.0, low=99.0, high=101.0, volume=100))
    buf.append(make_candle(101.0, low=100.0, high=102.0, volume=100))
    buf.append(make_candle(102.0, low=101.0, high=103.0, volume=100))
    buf.append(make_candle(103.0, low=102.0, high=104.0, volume=100))
    # range > 0.3%, vol spike 3x > 1.5x
    buf.append(make_candle(104.0, low=103.0, high=105.0, volume=300))
    res = score_momentum(buf)
    assert res.status == "GREEN"
    assert res.points == 1

def test_score_momentum_red_choppy(make_candle):
    buf = deque(maxlen=20)
    for _ in range(20):
        # All completely flat/choppy
        buf.append(make_candle(100.0, low=99.9, high=100.1, volume=100))
    res = score_momentum(buf)
    assert res.status == "RED"
    assert res.points == 0

def test_score_oi_flow_bullish(make_atm):
    atm = make_atm(22000, ce_oi_change=1000, pe_oi_change=-500)
    res = score_oi_flow(atm)
    assert res.status == "GREEN"
    assert "Bullish" in res.detail

def test_score_oi_flow_bearish(make_atm):
    atm = make_atm(22000, ce_oi_change=-1000, pe_oi_change=500)
    res = score_oi_flow(atm)
    assert res.status == "GREEN"
    assert "Bearish" in res.detail

def test_score_oi_flow_neutral(make_atm):
    atm = make_atm(22000, ce_oi_change=1000, pe_oi_change=1000)
    res = score_oi_flow(atm)
    assert res.status == "RED"
    assert res.points == 0

def test_score_gamma_theta_dte3(make_atm):
    atm = make_atm(22000, ce_gamma=0.2, ce_theta=-1.0) # ratio = 0.2
    # dte=3, green_thresh=0.10
    res = score_gamma_theta(atm, 3)
    assert res.status == "GREEN"

def test_score_gamma_theta_dte1_strict(make_atm):
    atm = make_atm(22000, ce_gamma=0.2, ce_theta=-1.0) # ratio = 0.2
    # dte=1, green_thresh=0.25, yellow_thresh=0.15
    res = score_gamma_theta(atm, 1)
    assert res.status == "YELLOW"

def test_score_pdhl_breakout_green(mock_now, mock_date):
    prev = PreviousDayLevels(symbol="NIFTY", trade_date=mock_date, prev_day_high=22000, prev_day_low=21800, fetched_at=mock_now)
    res = score_pdhl_breakout(22100, prev)
    assert res.status == "GREEN"

def test_score_pdhl_breakout_red(mock_now, mock_date):
    prev = PreviousDayLevels(symbol="NIFTY", trade_date=mock_date, prev_day_high=22000, prev_day_low=21800, fetched_at=mock_now)
    res = score_pdhl_breakout(21900, prev)
    assert res.status == "RED"

def test_score_move_ratio_green(make_candle, make_atm):
    # implied straddle is 100+100 = 200. spot = 22000 => implied = ~0.9%
    atm = make_atm(22000, ce_ltp=100, pe_ltp=100)
    buf = deque([make_candle(22000)] * 29, maxlen=30)
    # 300 pts realized high-low => > 1.36% realized move. > implied so > 1.0 => GREEN
    buf.append(make_candle(22150, low=21850, high=22150))
    res = score_move_ratio(atm, buf)
    assert res.status == "GREEN"

def test_score_vwap_distance_green(make_candle):
    buf = deque([make_candle(22000, vwap=22000)], maxlen=30)
    res = score_vwap_distance(22010, buf) # 10 pts distance (~0.04% < 0.2%)
    assert res.status == "GREEN"

def test_score_vwap_distance_red(make_candle):
    buf = deque([make_candle(22000, vwap=22000)], maxlen=30)
    res = score_vwap_distance(22500, buf) # 500 pts distance (> 2.0%)
    assert res.status == "RED"
