from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

print("Alpha Lab setup check")
print("---------------------")
print(f"Working directory: {Path.cwd()}")
print(f"ALPACA_API_KEY present: {bool(os.getenv('ALPACA_API_KEY'))}")
print(f"ALPACA_SECRET_KEY present: {bool(os.getenv('ALPACA_SECRET_KEY'))}")
print(f"ALPACA_PAPER: {os.getenv('ALPACA_PAPER', 'true')}")
print(f"ALLOW_ORDERS: {os.getenv('ALLOW_ORDERS', 'false')}")

if os.getenv("ALLOW_ORDERS", "false").lower() == "true":
    raise SystemExit("SAFETY STOP: ALLOW_ORDERS must remain false during research setup.")

if not os.getenv("ALPACA_API_KEY") or not os.getenv("ALPACA_SECRET_KEY"):
    print("\nNext: copy .env.example to .env and add a SEPARATE Alpaca paper account key/secret.")
else:
    print("\nCredentials are present. Next run scripts/fetch_data.py.")
