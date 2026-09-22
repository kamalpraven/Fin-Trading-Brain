import pandas as pd
from alpha_lab.backtest import BacktestConfig,run_single_symbol

def test_next_open_entry():
    d=pd.DataFrame({"timestamp":pd.date_range("2026-01-01",periods=6,freq="B",tz="UTC"),"open":[100,101,102,103,104,105],"close":[100,101,102,103,104,105]})
    s=pd.Series([True,False,False,False,False,False]); _,t,_=run_single_symbol(d,s,BacktestConfig(max_hold_days=1,stop_loss_pct=.5,slippage_bps=0)); assert len(t)==1 and t.iloc[0].entry_price==101
