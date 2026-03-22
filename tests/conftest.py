import pytest
from datetime import datetime, date
from kairos.models import (
    OHLCVCandle,
    OptionChainRow,
    PreviousDayLevels,
    ATMStrikes,
)

@pytest.fixture
def mock_now():
    return datetime(2026, 3, 22, 10, 0, 0)

@pytest.fixture
def mock_date():
    return date(2026, 3, 22)

@pytest.fixture
def make_candle(mock_now):
    def _make(close, volume=1000, high=None, low=None, vwap=None):
        return OHLCVCandle(
            timestamp=mock_now,
            symbol="NIFTY",
            open=close,
            high=high if high is not None else close,
            low=low if low is not None else close,
            close=close,
            volume=volume,
            vwap=vwap if vwap is not None else close
        )
    return _make

@pytest.fixture
def make_option_row(mock_now, mock_date):
    def _make(strike, opt_type, iv=0.15, gamma=0.0, theta=0.0, oi_change=0, ltp=100.0):
        return OptionChainRow(
            timestamp=mock_now,
            symbol="NIFTY",
            expiry=mock_date,
            strike=strike,
            option_type=opt_type,
            iv=iv,
            delta=0.5,
            gamma=gamma,
            theta=theta,
            vega=0.0,
            oi=1000,
            oi_change=oi_change,
            volume=500,
            ltp=ltp,
            bid=ltp,
            ask=ltp
        )
    return _make

@pytest.fixture
def make_atm(make_option_row):
    def _make(spot_price, ce_iv=0.15, ce_gamma=0.0, ce_theta=0.0, ce_oi_change=0, pe_oi_change=0, ce_ltp=100.0, pe_ltp=100.0):
        atm_strike = round(spot_price / 50) * 50
        ce = make_option_row(atm_strike, "CE", iv=ce_iv, gamma=ce_gamma, theta=ce_theta, oi_change=ce_oi_change, ltp=ce_ltp)
        pe = make_option_row(atm_strike, "PE", oi_change=pe_oi_change, ltp=pe_ltp)
        return ATMStrikes(atm_strike=atm_strike, ce=ce, pe=pe, spot_price=spot_price)
    return _make
