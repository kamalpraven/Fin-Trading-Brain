import math
import pandas as pd

from alpha_lab.portfolio_backtest import PortfolioBacktestConfig, run_portfolio_backtest
from alpha_lab.regime import RegimeSpec, build_regime_controls, trend_state, volatility_state


def market_bars(n=70):
    dates=pd.bdate_range('2026-01-01', periods=n, tz='UTC')
    rows=[]
    for sym in ['AAA','QQQ','SPY']:
        for i,ts in enumerate(dates):
            if sym == 'QQQ': close = 100+i if i < 55 else 80
            elif sym == 'SPY': close = 100+i*0.5
            else: close = 100
            rows.append({'symbol':sym,'timestamp':ts,'open':close,'high':close+1,'low':close-1,'close':close,'volume':1000})
    return pd.DataFrame(rows)


def alpha_bars(n=5):
    d=pd.bdate_range('2026-01-01', periods=n, tz='UTC')
    return pd.DataFrame({'symbol':['AAA']*n,'timestamp':d,'open':[100]*n,'high':[101]*n,'low':[99]*n,'close':[100]*n,'volume':[1]*n})


def signals(df):
    s=df[['symbol','timestamp']].copy(); s['entry_signal']=[True]+[False]*(len(df)-1); s['signal_strength']=0; return s


def test_qqq_sma_regime_state_and_no_lookahead_current_close_only():
    df=market_bars()
    st=trend_state(df,'QQQ',50)
    assert 'qqq_above_sma50' in st.columns
    # Mutating a future close must not change an earlier state.
    before=st.loc[54,'qqq_above_sma50']
    df2=df.copy(); df2.loc[(df2.symbol=='QQQ') & (df2.timestamp==df2.timestamp.max()), 'close']=9999
    after=trend_state(df2,'QQQ',50).loc[54,'qqq_above_sma50']
    assert before == after


def test_spy_sma_regime_state():
    st=trend_state(market_bars(),'SPY',50)
    assert bool(st.iloc[-1]['spy_above_sma50'])


def test_high_vol_regime_classification_no_future_quantile():
    df=market_bars(80)
    st=volatility_state(df,'QQQ',10,.67)
    assert 'high_vol' in st.columns
    early=st.high_vol.iloc[20]
    df2=df.copy(); df2.loc[(df2.symbol=='QQQ') & (df2.timestamp==df2.timestamp.max()), 'close']=10000
    assert early == volatility_state(df2,'QQQ',10,.67).high_vol.iloc[20]


def test_hard_gate_prevents_new_entries():
    df=alpha_bars()
    ctrl=df[['timestamp']].copy(); ctrl['allow_entries']=[False]*len(df); ctrl['exposure_multiplier']=0.0
    _,tr,*_=run_portfolio_backtest(df,signals(df),PortfolioBacktestConfig(slippage_bps=0),controls=ctrl)
    assert len(tr)==0


def test_reduced_exposure_correct_position_sizing_and_no_leverage():
    df=alpha_bars()
    ctrl=df[['timestamp']].copy(); ctrl['allow_entries']=True; ctrl['exposure_multiplier']=0.5
    eq,tr,*_=run_portfolio_backtest(df,signals(df),PortfolioBacktestConfig(fraction_per_trade=.2,max_hold_days=1,slippage_bps=0),controls=ctrl)
    assert math.isclose(tr.iloc[0].allocation, 10000)
    assert eq.gross_exposure.max() <= 1.0


def test_baseline_unchanged_when_controls_disabled_and_deterministic():
    df=alpha_bars()
    a=run_portfolio_backtest(df,signals(df),PortfolioBacktestConfig(max_hold_days=1,slippage_bps=0))
    ctrl=df[['timestamp']].copy(); ctrl['allow_entries']=True; ctrl['exposure_multiplier']=1.0
    b=run_portfolio_backtest(df,signals(df),PortfolioBacktestConfig(max_hold_days=1,slippage_bps=0),controls=ctrl)
    pd.testing.assert_frame_equal(a[0], b[0])
    pd.testing.assert_frame_equal(b[0], run_portfolio_backtest(df,signals(df),PortfolioBacktestConfig(max_hold_days=1,slippage_bps=0),controls=ctrl)[0])


def test_build_regime_controls_reduce():
    c=build_regime_controls(market_bars(), RegimeSpec('x','trend_reduce','QQQ',50,below_multiplier=.5))
    assert c.exposure_multiplier.min() <= .5
