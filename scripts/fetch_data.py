import argparse
from alpha_lab.data import fetch_daily_bars,cache_bars
p=argparse.ArgumentParser(); p.add_argument("--symbols",nargs="+",required=True); p.add_argument("--start",required=True); p.add_argument("--end",required=True); p.add_argument("--name",default="daily_bars"); a=p.parse_args()
df=fetch_daily_bars(a.symbols,a.start,a.end); print(f"saved {len(df):,} rows -> {cache_bars(df,a.name)}")
