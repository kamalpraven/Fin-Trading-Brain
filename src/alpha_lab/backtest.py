from dataclasses import dataclass
import pandas as pd
from .metrics import summarize

@dataclass
class BacktestConfig:
    initial_cash: float=100000.0
    fraction_per_trade: float=0.20
    max_hold_days: int=3
    stop_loss_pct: float=0.04
    slippage_bps: float=5.0
    reverse_day_exit: bool=False

def run_single_symbol(df,entry_signal,cfg):
    x=df.sort_values("timestamp").reset_index(drop=True).copy(); sig=pd.Series(entry_signal).reset_index(drop=True).fillna(False)
    cash=cfg.initial_cash; shares=0.0; entry_price=None; entry_i=None; trades=[]; eq=[]; slip=cfg.slippage_bps/10000
    for i,row in x.iterrows():
        if shares>0 and i>0:
            prev=x.iloc[i-1]; held=i-entry_i; prev_close=float(prev.close)
            stop=prev_close<=entry_price*(1-cfg.stop_loss_pct)
            reverse=cfg.reverse_day_exit and i>=2 and float(x.iloc[i-1].close)<float(x.iloc[i-2].close)
            if stop or reverse or held>=cfg.max_hold_days:
                px=float(row.open)*(1-slip); cash+=shares*px; trades.append({"entry_time":x.iloc[entry_i].timestamp,"exit_time":row.timestamp,"entry_price":entry_price,"exit_price":px,"pnl_pct":px/entry_price-1,"hold_bars":held}); shares=0; entry_price=None; entry_i=None
        if shares==0 and i>0 and bool(sig.iloc[i-1]):
            px=float(row.open)*(1+slip); alloc=cash*cfg.fraction_per_trade; shares=alloc/px; cash-=alloc; entry_price=px; entry_i=i
        eq.append((row.timestamp,cash+shares*float(row.close)))
    equity=pd.Series([v for _,v in eq],index=pd.to_datetime([t for t,_ in eq]),name="equity"); tdf=pd.DataFrame(trades)
    return equity,tdf,summarize(equity,tdf)
