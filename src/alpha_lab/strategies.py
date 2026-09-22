def semi_momentum_signal(df,lookback_days=2):
    lag=f"close_lag{lookback_days}"
    return (df["close"]>df["close_lag1"]) & (df["close"]>df[lag])

def qqq_pullback_signal(df):
    return (df["close"]<df["close_lag1"]) & (df["close"]>df["close_lag5"])

def catalyst_proxy_signal(df,min_daily_return=0.02):
    return df["ret_1d"]>=min_daily_return
