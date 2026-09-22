def rolling_window_returns(equity,window=10): return equity/equity.shift(window)-1

def summarize_windows(s):
    x=s.dropna()
    if x.empty: return {}
    return {"mean_10d":float(x.mean()),"median_10d":float(x.median()),"p10":float(x.quantile(.1)),"p90":float(x.quantile(.9)),"prob_positive":float((x>0).mean()),"worst":float(x.min()),"best":float(x.max())}
