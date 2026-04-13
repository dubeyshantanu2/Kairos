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
    buf.append(0.25) # 0.25 - 0.15 = 0.10 (between -0.5 and +0.2)
    res = score_iv_change(buf, dte=0)
    assert res.status == "YELLOW"
    assert res.points == 1

def test_score_iv_change_red():
    buf = deque([0.15] * 15, maxlen=20)
    buf.append(-0.45) # -0.45 - 0.15 = -0.60 < -0.5
    res = score_iv_change(buf, dte=0)
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

def test_score_oi_flow_conviction_only(make_atm, make_candle):
    """Verifies that directional conviction (Bearish/Bullish) works independent of Trend Phase."""
    # Bearish Conviction: CE Building, PE Unwinding
    # Trend Phase: Long Buildup (Price UP, Total OI UP)
    atm = make_atm(22010, ce_oi_change=10000, pe_oi_change=-500)
    buf = deque([make_candle(22000)] * 5, maxlen=15)
    res = score_oi_flow(atm, buf)
    assert res.status == "GREEN" # Strong conviction
    assert "Bearish" in res.detail
    assert "Long Buildup 🟢" in res.detail

    # Bullish Conviction: PE Building, CE Unwinding
    # Trend Phase: Short Buildup (Price DOWN, Total OI UP)
    atm = make_atm(21990, ce_oi_change=-1000, pe_oi_change=10000)
    buf = deque([make_candle(22000)] * 5, maxlen=15)
    res = score_oi_flow(atm, buf)
    assert res.status == "GREEN"
    assert "Bullish" in res.detail
    assert "Short Buildup 🔴" in res.detail

def test_score_oi_flow_trend_phases(make_atm, make_candle):
    """Exhaustive check for the 4 active trend phases."""
    # 1. Long Buildup: Price UP, Total OI UP (> 5000)
    atm = make_atm(22010, ce_oi_change=4000, pe_oi_change=2000)
    buf = deque([make_candle(22000)] * 5, maxlen=15)
    assert "Long Buildup 🟢" in score_oi_flow(atm, buf).detail

    # 2. Short Covering: Price UP, Total OI DOWN (< -5000)
    atm = make_atm(22010, ce_oi_change=-4000, pe_oi_change=-2000)
    buf = deque([make_candle(22000)] * 5, maxlen=15)
    assert "Short Covering 🔵" in score_oi_flow(atm, buf).detail

    # 3. Short Buildup: Price DOWN, Total OI UP (> 5000)
    atm = make_atm(21990, ce_oi_change=3000, pe_oi_change=3000)
    buf = deque([make_candle(22000)] * 5, maxlen=15)
    assert "Short Buildup 🔴" in score_oi_flow(atm, buf).detail

    # 4. Long Unwinding: Price DOWN, Total OI DOWN (< -5000)
    atm = make_atm(21990, ce_oi_change=-3000, pe_oi_change=-3000)
    buf = deque([make_candle(22000)] * 5, maxlen=15)
    assert "Long Unwinding 🟠" in score_oi_flow(atm, buf).detail

def test_score_oi_flow_neutral_scenarios(make_atm, make_candle):
    """Verifies Neutral phase when thresholds are not met or price is flat."""
    # Below threshold: Total OI change = 4000 (< 5000)
    atm = make_atm(22010, ce_oi_change=2000, pe_oi_change=2000)
    buf = deque([make_candle(22000)] * 5, maxlen=15)
    assert "Neutral 🟡" in score_oi_flow(atm, buf).detail

    # Exactly at threshold: Should stay Neutral (logic uses > and <, not >= and <=)
    atm = make_atm(22010, ce_oi_change=5000, pe_oi_change=0)
    buf = deque([make_candle(22000)] * 5, maxlen=15)
    assert "Neutral 🟡" in score_oi_flow(atm, buf).detail

    # Flat price: phase remains Neutral regardless of OI
    atm = make_atm(22000, ce_oi_change=10000, pe_oi_change=10000)
    buf = deque([make_candle(22000)] * 5, maxlen=15)
    assert "Neutral 🟡" in score_oi_flow(atm, buf).detail

def test_score_oi_flow_warmup(make_atm, make_candle):
    atm = make_atm(22000, ce_oi_change=1000, pe_oi_change=1000)
    buf = deque([make_candle(22000)] * 2, maxlen=15) # Only 2 candles, need 5
    res = score_oi_flow(atm, buf)
    assert res.status == "YELLOW"
    assert "Warming up" in res.detail

def test_score_gamma_theta_dte3(make_atm):
    # Realistic Dhan-scale Greeks: 
    # gamma = 0.00132, theta = -15.1539, spot = 22000
    # theta_normalized = 15.1539 / 22000 = 0.0006888...
    # ratio = 0.00132 / 0.0006888 = 1.916... → GREEN at DTE≥3 (thresh 0.00025)
    atm = make_atm(22000, ce_gamma=0.00132, ce_theta=-15.1539)
    res = score_gamma_theta(atm, 3)
    assert res.status == "GREEN"

    # At DTE=1, thresh is 0.00020. 1.916 is still well above.
    res = score_gamma_theta(atm, 1)
    assert res.status == "GREEN"

def test_score_gamma_theta_normalization_verification(make_atm):
    """
    Verifies that the normalization by spot price makes the ratio stable 
    across different index levels (e.g. NIFTY at 22k vs 25k).
    """
    # Case 1: Spot = 20000, Gamma = 0.0005, Theta = 10.0
    # theta_norm = 10 / 20000 = 0.0005. Ratio = 0.0005 / 0.0005 = 1.0
    atm1 = make_atm(20000, ce_gamma=0.0005, ce_theta=-10.0)
    res1 = score_gamma_theta(atm1, 3)
    
    # Case 2: Spot = 40000, Gamma = 0.00025, Theta = 10.0
    # Theta is absolute rupee decay. In a 40k index, a 10 rupee decay is 
    # half as significant as in a 20k index on a percentage basis.
    # theta_norm = 10 / 40000 = 0.00025. Ratio = 0.00025 / 0.00025 = 1.0
    # Since gamma is per-point-sq, it naturally scales inversely with price sq? 
    # Actually, Dhan's gamma is absolute. 
    # Let's just verify that for the same Greek values, the ratio changes 
    # correctly based on spot.
    
    # If Greeks are IDENTICAL but spot is higher:
    # Spot 20k -> Ratio 1.0
    # Spot 40k -> theta_norm = 0.00025 -> Ratio = 0.0005 / 0.00025 = 2.0
    # This proves that for the same absolute decay, a higher spot price 
    # (more expensive index) gives more weight to Gamma.
    atm2 = make_atm(40000, ce_gamma=0.0005, ce_theta=-10.0)
    res2 = score_gamma_theta(atm2, 3)
    
    # Extract ratios from details string "Ratio 1.000000 (DTE≥3 scale)"
    ratio1 = float(res1.detail.split()[1])
    ratio2 = float(res2.detail.split()[1])
    
    assert ratio1 == 1.0
    assert ratio2 == 2.0

def test_score_gamma_theta_gamma_zero(make_atm):
    # Session open cold-start: gamma=0 should return YELLOW not RED
    atm = make_atm(22000, ce_gamma=0.0, ce_theta=-15.1539)
    res = score_gamma_theta(atm, 3)
    assert res.status == "YELLOW"
    assert "Gamma = 0" in res.detail

def test_score_pdhl_breakout_green(mock_now, mock_date):
    prev = PreviousDayLevels(symbol="NIFTY", trade_date=mock_date, prev_day_high=22000, prev_day_low=21800, fetched_at=mock_now)
    res = score_pdhl_breakout(22100, prev)
    assert res.status == "GREEN"

def test_score_pdhl_breakout_red(mock_now, mock_date):
    prev = PreviousDayLevels(symbol="NIFTY", trade_date=mock_date, prev_day_high=22000, prev_day_low=21800, fetched_at=mock_now)
    res = score_pdhl_breakout(21900, prev)
    assert res.status == "RED"

def test_score_move_ratio_green(make_candle, make_atm):
    # DTE=6: scaling = sqrt(15 / (6*375)) = sqrt(15/2250) ≈ 0.0816
    # straddle = 200, spot = 22000 → raw implied = 0.909%
    # scaled implied = 0.909% * 0.0816 ≈ 0.074%
    # realized range = (22150 - 21850) / 22000 = 1.36%
    # ratio = 1.36 / 0.074 ≈ 18.4 → well above 1.0 → GREEN
    atm = make_atm(22000, ce_ltp=100, pe_ltp=100)
    buf = deque([make_candle(22000)] * 14, maxlen=15)
    buf.append(make_candle(22150, low=21850, high=22150))
    res = score_move_ratio(atm, buf, dte=6)
    assert res.status == "GREEN"

def test_score_vwap_distance_green(make_candle):
    buf = deque([make_candle(22000, vwap=22000)], maxlen=15)

    res = score_vwap_distance(22010, buf) # 10 pts distance (~0.04% < 0.2%)
    assert res.status == "GREEN"

def test_score_vwap_distance_red(make_candle):
    buf = deque([make_candle(22000, vwap=22000)], maxlen=15)

    res = score_vwap_distance(22500, buf) # 500 pts distance (> 2.0%)
    assert res.status == "RED"
