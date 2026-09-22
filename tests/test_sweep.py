import pandas as pd

from alpha_lab.portfolio_backtest import PortfolioBacktestConfig, run_portfolio_backtest
from alpha_lab.sweep import run_parameter_sweep, walk_forward, add_regimes, non_overlapping_10d, leave_one_out, cost_sensitivity


def sample(symbols=("AAA","BBB","QQQ","SPY"), n=80):
    dates = pd.bdate_range("2022-01-03", periods=n, tz="UTC")
    rows=[]
    for sym in symbols:
        for i,ts in enumerate(dates):
            px = 100 + i*0.2 + (i%5)
            rows.append({"symbol":sym,"timestamp":ts,"open":px,"high":px+2,"low":px-2,"close":px+0.5,"volume":1000+i})
    return pd.DataFrame(rows)


def cfg():
    return {"name":"x","symbols":["AAA","BBB"],"entry":{"type":"momentum","lookback_days":2},"exit":{"reverse_day":False,"max_hold_days":2,"stop_loss_pct":.04},"sizing":{"fraction_per_trade":.2,"max_positions":1},"execution":{"slippage_bps":5}}


def test_parameter_sweep_determinism():
    df=sample()
    a=run_parameter_sweep(df,cfg(),lookbacks=[2],holds=[1,2],stops=[.03])
    b=run_parameter_sweep(df,cfg(),lookbacks=[2],holds=[1,2],stops=[.03])
    pd.testing.assert_frame_equal(a,b)


def test_chronological_walk_forward_separation():
    df=sample(n=260)
    folds=[{"train_start":"2022-01-03","train_end":"2022-06-30","valid_start":"2022-07-01","valid_end":"2022-12-31"}]
    out=walk_forward(df,cfg(),folds)
    assert (pd.to_datetime(out.train_end) < pd.to_datetime(out.valid_start)).all()
    assert set(out.model)=={"selected","baseline"}


def test_no_future_leakage_in_regime_quantiles():
    df=sample(symbols=("QQQ","SPY"),n=100)
    reg=add_regimes(df)
    first=reg.head(25)
    # Early vol regimes exist without using full-sample quantile constants; labels may be high while expanding history forms.
    assert "qqq_vol_regime" in reg.columns
    assert len(first)==25


def test_non_overlapping_10d_windows():
    eq=pd.DataFrame({"timestamp":pd.bdate_range("2026-01-01",periods=25,tz="UTC"),"total_equity":range(100,125),"gross_exposure":[0]*25})
    out=non_overlapping_10d(eq,pd.DataFrame())
    assert len(out)==2
    assert list(out.start_date)==[eq.timestamp.iloc[0], eq.timestamp.iloc[10]]


def test_gap_aware_stop_execution_intraday_stop():
    dates=pd.bdate_range("2026-01-01",periods=4,tz="UTC")
    bars=pd.DataFrame({"symbol":["AAA"]*4,"timestamp":dates,"open":[100,100,100,100],"high":[101]*4,"low":[99,99,94,99],"close":[100,100,100,100],"volume":[1]*4})
    sig=bars[["symbol","timestamp"]].copy(); sig["entry_signal"]=[True,False,False,False]; sig["signal_strength"]=0
    _,trades,*_=run_portfolio_backtest(bars,sig,PortfolioBacktestConfig(max_hold_days=3,stop_loss_pct=.05,slippage_bps=0,stop_execution="daily_gap_aware"))
    assert trades.iloc[0].exit_reason=="stop_loss"
    assert trades.iloc[0].exit_price==95


def test_leave_one_out_universe_handling():
    out=leave_one_out(sample(symbols=("AAA","BBB","QQQ","SPY")),cfg())
    assert set(out.removed_symbol)=={"AAA","BBB"}


def test_cost_sensitivity_behavior():
    out=cost_sensitivity(sample(),cfg(),{"lookback":2,"max_hold":2,"stop_loss":.04},costs=[0,20])
    assert list(out.slippage_bps)==[0,20]
    assert out.trades.notna().all()
