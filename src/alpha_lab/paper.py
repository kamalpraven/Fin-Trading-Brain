import os
from dotenv import load_dotenv
load_dotenv()

def assert_orders_enabled():
    if os.getenv("ALLOW_ORDERS","false").lower()!="true":
        raise RuntimeError("Order submission disabled. Use a separate shadow paper account; never the dedicated Conviction competition account.")
