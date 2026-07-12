"""Regenerate examples/messy_vendors.xlsx — a vendor ledger with
deliberate, documented errors that every core pillar can catch.

Run:  python examples/make_messy_vendors.py
"""

from __future__ import annotations

import os
import random

import pandas as pd

random.seed(42)

CITIES = ["Mumbai", "Delhi", "Bengaluru", "Pune", "Chennai"]
STATES = ["27", "07", "29", "27", "33"]

rows = []
for i in range(1, 51):
    pan = f"{''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ', k=5))}{random.randint(1000, 9999)}F"
    city_idx = random.randrange(len(CITIES))
    rows.append({
        "vendor_id": f"VND-{i:04d}",
        "vendor_name": f"{random.choice(['Sharma', 'Patel', 'Iyer', 'Khan', 'Gupta', 'Reddy'])} "
                       f"{random.choice(['Traders', 'Enterprises', 'Industries', 'Exports', 'Solutions'])} "
                       f"{i}",
        "gstin": f"{STATES[city_idx]}{pan}1Z{random.choice('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')}",
        "pan": pan,
        "email": f"vendor{i}@example.com",
        "phone": f"{random.choice('6789')}{random.randint(100000000, 999999999)}",
        "city": CITIES[city_idx],
        "amount": round(random.uniform(5_000, 95_000), 2),
        "invoice_date": f"2026-{random.randint(1, 6):02d}-{random.randint(1, 28):02d}",
    })

df = pd.DataFrame(rows)

# --- Deliberate errors ------------------------------------------------
# Invalid GSTINs (wrong length / lowercase / missing Z)
df.loc[3, "gstin"] = "27AAPFU0939F1AV"     # no 'Z' in 14th position
df.loc[11, "gstin"] = "27aapfu0939f1zv"    # lowercase
df.loc[19, "gstin"] = "27AAPFU0939F1Z"     # too short

# Invalid PANs
df.loc[7, "pan"] = "AB1234567Z"            # wrong structure
df.loc[23, "pan"] = "AAPFU0939"            # too short

# Bad emails / phone
df.loc[5, "email"] = "not-an-email"
df.loc[14, "email"] = "vendor15@@example..com"
df.loc[27, "phone"] = "12345"              # not a valid Indian mobile

# Missing values
df.loc[9, "email"] = None
df.loc[31, "amount"] = None
df.loc[40, "city"] = None

# Duplicate PAN (two vendors sharing one identity)
df.loc[35, "pan"] = df.loc[2, "pan"]

# Exact duplicate row
df.loc[45] = df.loc[12]

# Near-duplicate row (same vendor, one-letter typo in the name)
dup = df.loc[20].copy()
dup["vendor_name"] = str(dup["vendor_name"]).replace("a", "e", 1)
df.loc[46] = dup

# Amount outlier: two orders of magnitude above everything else
df.loc[17, "amount"] = 9_750_000.00

# Pattern break in vendor_id (all VND-9999 except this one)
df.loc[29, "vendor_id"] = "VENDOR_30"

# Rare category in city
df.loc[43, "city"] = "Ranchi"

out = os.path.join(os.path.dirname(__file__), "messy_vendors.xlsx")
df.to_excel(out, index=False)
print(f"Wrote {out}: {len(df)} rows, {len(df.columns)} columns")
