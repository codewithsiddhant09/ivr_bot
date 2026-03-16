#!/usr/bin/env python3
import json, sys, urllib.request, urllib.error
from pathlib import Path

# Load .env
env = {}
for line in (Path(__file__).parent / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")

BASE_URL      = env["BASE_URL"].rstrip("/")
API_KEY       = env["RAG_SYSTEM_KEY"]
COLLECTION_ID = env["COLLECTION_ID"]
QUESTION      = " ".join(sys.argv[1:])

if not QUESTION:
    print('Usage: python3 api_test.py "Your question here"')
    sys.exit(1)

payload = json.dumps({"collectionId": COLLECTION_ID, "question": QUESTION}).encode()

for mode, path in [("RETRIEVE", "/api/query/retrieve"), ("FULL RAG", "/api/query")]:
    url = BASE_URL + path
    req = urllib.request.Request(url, data=payload,
          headers={"Content-Type": "application/json", "X-API-Key": API_KEY}, method="POST")
    print(f"\n── {mode}  →  {url}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"   Status : {r.status}")
            print(json.dumps(json.loads(r.read()), indent=2))
    except urllib.error.HTTPError as e:
        print(f"   Status : {e.code}")
        print(e.read().decode())
