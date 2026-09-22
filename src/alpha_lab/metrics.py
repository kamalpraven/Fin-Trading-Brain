import numpy as np

def max_drawdown(equity):
    return float((equity/equity.cummax()-1).min())

def sharpe(r,periods=252):
    r=r.dropna()
    return float(np.sqrt(periods)*r.mean()/r.std(ddof=1)) if len(r)>1 and r.std(ddof=1)>0 else float("nan")

def summarize(equity,trades):
    daily=equity.pct_change().dropna(); total=float(equity.iloc[-1]/equity.iloc[0]-1)
    if len(trades):
        win=float((trades.pnl_pct>0).mean()); gp=trades.loc[trades.pnl_pct>0,"pnl_pct"].sum(); gl=-trades.loc[trades.pnl_pct<0,"pnl_pct"].sum(); pf=float(gp/gl) if gl>0 else float("inf")
    else: win=float("nan"); pf=float("nan")
    return {"total_return":total,"max_drawdown":max_drawdown(equity),"sharpe":sharpe(daily),"trades":int(len(trades)),"win_rate":win,"profit_factor":pf}
