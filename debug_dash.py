"""Inspect the actual dash API response structure."""
import os, sys, json, requests

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "williamhgates"
LI_AT = os.environ.get("LI_AT", "")

s = requests.Session()
s.max_redirects = 5
s.cookies.set("li_at", LI_AT, domain=".linkedin.com")
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Li-Lang": "en_US",
    "X-RestLi-Protocol-Version": "2.0.0",
    "Accept": "application/vnd.linkedin.normalized+json+2.1",
})

# Get CSRF
feed = s.get("https://www.linkedin.com/feed/", timeout=15)
for c in list(feed.cookies) + list(s.cookies):
    if c.name == "JSESSIONID":
        csrf = c.value.strip('"')
        s.headers["csrf-token"] = csrf
        s.cookies.set("JSESSIONID", f'"{csrf}"', domain=".linkedin.com")
        break

r = s.get(
    "https://www.linkedin.com/voyager/api/identity/dash/profiles",
    params={
        "q": "memberIdentity",
        "memberIdentity": USERNAME,
        "decorationId": "com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-93",
    },
    timeout=20,
)

data = r.json()

print("=== DATA keys ===")
print(json.dumps({k: str(v)[:120] for k, v in data.get("data", {}).items()}, indent=2))

print(f"\n=== INCLUDED ({len(data.get('included', []))} items) ===")
for i, item in enumerate(data.get("included", [])):
    t = item.get("$type", "?")
    keys = [k for k in item.keys() if not k.startswith("$") and k not in ("paging", "entityUrn", "$recipeTypes")]
    print(f"\n[{i:02d}] $type: {t}")
    print(f"     entityUrn: {item.get('entityUrn', '')[:80]}")
    # Print non-meta fields with values
    for k in keys[:15]:
        v = item[k]
        if isinstance(v, str):
            print(f"     {k}: {v[:100]}")
        elif isinstance(v, (int, float, bool)):
            print(f"     {k}: {v}")
        elif isinstance(v, list):
            print(f"     {k}: list[{len(v)}]", end="")
            if v and isinstance(v[0], dict):
                print(f"  first_keys={list(v[0].keys())[:6]}", end="")
            elif v:
                print(f"  [{str(v[0])[:60]}]", end="")
            print()
        elif isinstance(v, dict):
            print(f"     {k}: dict keys={list(v.keys())[:8]}")

# Also save full response for manual inspection
with open("dash_response.json", "w") as f:
    json.dump(data, f, indent=2)
print("\n\nFull response saved to dash_response.json")
