"""
Run this to see exactly what each LinkedIn API endpoint returns.
Usage:  python debug_probe.py [linkedin_username]
Requires LI_AT env var to be set.
"""
import os, sys, re, json, requests

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "williamhgates"
LI_AT = os.environ.get("LI_AT", "")
if not LI_AT:
    print("ERROR: LI_AT env var not set"); sys.exit(1)

VOYAGER = "https://www.linkedin.com/voyager/api"

# ── Build session ─────────────────────────────────────────────────────────────
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
print("── Getting CSRF token from /feed/ ──────────────────────────────────────")
try:
    feed = s.get("https://www.linkedin.com/feed/", timeout=15)
    print(f"  /feed/ status: {feed.status_code}  final_url: {feed.url}")
    csrf = ""
    for c in feed.cookies:
        if c.name == "JSESSIONID":
            csrf = c.value.strip('"')
    for c in s.cookies:
        if c.name == "JSESSIONID":
            csrf = c.value.strip('"')
    print(f"  CSRF token: {csrf[:30]}..." if csrf else "  CSRF token: NOT FOUND")
    if csrf:
        s.headers["csrf-token"] = csrf
        s.cookies.set("JSESSIONID", f'"{csrf}"', domain=".linkedin.com")
except Exception as e:
    print(f"  ERROR: {e}")

def probe(label, url, params=None):
    print(f"\n── {label} ─────────────────────────")
    print(f"  URL: {url}")
    if params: print(f"  Params: {params}")
    try:
        r = s.get(url, params=params, timeout=20)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            try:
                d = r.json()
                keys = list(d.keys()) if isinstance(d, dict) else f"list[{len(d)}]"
                print(f"  Top-level keys: {keys}")
                # Show first-level data preview
                if isinstance(d, dict):
                    for k, v in list(d.items())[:5]:
                        if isinstance(v, (str, int, float, bool)):
                            print(f"    {k}: {v}")
                        elif isinstance(v, list):
                            print(f"    {k}: list[{len(v)}]", end="")
                            if v and isinstance(v[0], dict):
                                print(f"  first item keys: {list(v[0].keys())[:8]}")
                            else:
                                print()
                        elif isinstance(v, dict):
                            print(f"    {k}: dict keys={list(v.keys())[:6]}")
            except Exception:
                print(f"  Body (first 500 chars): {r.text[:500]}")
        else:
            print(f"  Body: {r.text[:300]}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")

# Strategy 1: individual sub-endpoints
probe("S1a: basic profile", f"{VOYAGER}/identity/profiles/{USERNAME}")
probe("S1b: positions",     f"{VOYAGER}/identity/profiles/{USERNAME}/positions", {"count":10,"start":0})
probe("S1c: educations",    f"{VOYAGER}/identity/profiles/{USERNAME}/educations", {"count":10,"start":0})
probe("S1d: skills",        f"{VOYAGER}/identity/profiles/{USERNAME}/skills",    {"count":100,"start":0})

# Strategy 2: dash API
for dec_suffix in ["93", "91", "95"]:
    probe(
        f"S2: dash decoration-{dec_suffix}",
        f"{VOYAGER}/identity/dash/profiles",
        {"q": "memberIdentity", "memberIdentity": USERNAME,
         "decorationId": f"com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-{dec_suffix}"},
    )

# Strategy 3: HTML page
print(f"\n── S3: HTML page ───────────────────────────────────────────────────────")
html_s = requests.Session()
html_s.cookies.update(s.cookies)
html_s.headers.update({
    "User-Agent": s.headers["User-Agent"],
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})
try:
    r = html_s.get(f"https://www.linkedin.com/in/{USERNAME}/", timeout=20)
    print(f"  Status: {r.status_code}  final_url: {r.url}")
    # Check for JSON-LD
    import re as _re
    ld_matches = _re.findall(r'<script type="application/ld\+json">(.*?)</script>', r.text, _re.S)
    print(f"  JSON-LD blocks found: {len(ld_matches)}")
    for i, m in enumerate(ld_matches):
        try:
            d = json.loads(m)
            print(f"    [{i}] @type={d.get('@type')}  keys={list(d.keys())[:8]}")
        except: pass
    # Check code tags
    code_matches = _re.findall(r'<code[^>]*>(.*?)</code>', r.text, _re.S)
    json_codes = 0
    entity_types = {}
    for m in code_matches:
        m = m.strip()
        if m.startswith('{'):
            try:
                d = json.loads(m)
                if 'included' in d:
                    for e in d['included']:
                        t = e.get('$type','').split('.')[-1]
                        entity_types[t] = entity_types.get(t, 0) + 1
                json_codes += 1
            except: pass
    print(f"  JSON <code> blocks: {json_codes}")
    print(f"  Entity types in included: {dict(sorted(entity_types.items(), key=lambda x: -x[1])[:10])}")
    # og:title
    og = _re.search(r'<meta property="og:title" content="([^"]+)"', r.text)
    print(f"  og:title: {og.group(1) if og else 'NOT FOUND'}")
except Exception as e:
    print(f"  EXCEPTION: {e}")

print("\n── Done ────────────────────────────────────────────────────────────────")
