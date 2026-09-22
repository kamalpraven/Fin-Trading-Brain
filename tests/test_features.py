import pandas as pd
from alpha_lab.features import add_basic_features

def test_previous_high_is_shifted():
    d=pd.DataFrame({"symbol":["NVDA"]*25,"timestamp":pd.date_range("2026-01-01",periods=25,freq="B",tz="UTC"),"open":range(1,26),"high":range(1,26),"low":range(1,26),"close":range(1,26),"volume":[100]*25})
    o=add_basic_features(d); assert o.loc[10,"prev_10d_high_close"]==10
