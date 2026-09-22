import numpy as np

def add_basic_features(df):
    out=df.sort_values(["symbol","timestamp"]).copy(); g=out.groupby("symbol",group_keys=False)
    out["ret_1d"]=g["close"].pct_change()
    for n in (1,2,5): out[f"close_lag{n}"]=g["close"].shift(n)
    for n in (5,20,50): out[f"sma_{n}"]=g["close"].transform(lambda s,n=n:s.rolling(n).mean())
    out["prev_10d_high_close"]=g["close"].transform(lambda s:s.shift(1).rolling(10).max())
    out["prev_20d_avg_volume"]=g["volume"].transform(lambda s:s.shift(1).rolling(20).mean())
    out["vol_ratio_20"]=out["volume"]/out["prev_20d_avg_volume"]
    delta=g["close"].diff(); gain=delta.clip(lower=0); loss=-delta.clip(upper=0)
    ag=gain.groupby(out["symbol"]).transform(lambda s:s.rolling(14).mean())
    al=loss.groupby(out["symbol"]).transform(lambda s:s.rolling(14).mean())
    rs=ag/al.replace(0,np.nan); out["rsi_14"]=100-(100/(1+rs))
    return out
