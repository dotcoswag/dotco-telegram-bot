"""Probe whether extract_emails_and_contacts=true returns contact data on /search."""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

URL = "https://local-business-data.p.rapidapi.com/search"
HEADERS = {
    "x-rapidapi-key": os.getenv("RAPIDAPI_KEY"),
    "x-rapidapi-host": "local-business-data.p.rapidapi.com",
}

params = {
    "query": "coffee shop in Boulder, Colorado",
    "limit": 3,
    "offset": 0,
    "region": "us",
    "language": "en",
    "zoom": "13",
    "extract_emails_and_contacts": "true",
}

resp = requests.get(URL, headers=HEADERS, params=params, timeout=30)
print(f"HTTP {resp.status_code}")
data = resp.json()
results = data.get("data", [])
print(f"results: {len(results)}\n")

for i, biz in enumerate(results, 1):
    print(f"--- result {i}: {biz.get('name')} ---")
    print(f"  email field         : {biz.get('email')!r}")
    contacts = biz.get("emails_and_contacts") or {}
    print(f"  emails_and_contacts : {json.dumps(contacts, indent=2) if contacts else 'EMPTY'}")
    print(f"  top-level keys with contact-ish names:")
    for k in biz.keys():
        if any(tok in k.lower() for tok in ("email", "contact", "social", "instagram", "facebook", "linkedin")):
            print(f"    {k}: {biz[k]!r}")
    print()
