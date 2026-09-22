from pathlib import Path
import os
import pandas as pd
from dotenv import load_dotenv
load_dotenv()
DATA_DIR=Path("data"); DATA_DIR.mkdir(exist_ok=True)

def fetch_daily_bars(symbols,start,end):
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    key=os.getenv("ALPACA_API_KEY"); secret=os.getenv("ALPACA_SECRET_KEY")
    if not key or not secret: raise RuntimeError("Set Alpaca keys in .env")
    client=StockHistoricalDataClient(key,secret)
    req=StockBarsRequest(symbol_or_symbols=list(symbols),timeframe=TimeFrame.Day,start=pd.Timestamp(start,tz="UTC"),end=pd.Timestamp(end,tz="UTC"))
    df=client.get_stock_bars(req).df.reset_index()
    return df[["symbol","timestamp","open","high","low","close","volume"]].sort_values(["symbol","timestamp"]).reset_index(drop=True)

def cache_bars(df,name="daily_bars"):
    p=DATA_DIR/f"{name}.parquet"; df.to_parquet(p,index=False); return p

def load_cached(name="daily_bars"):
    return pd.read_parquet(DATA_DIR/f"{name}.parquet")
