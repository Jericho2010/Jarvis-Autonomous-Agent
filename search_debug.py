#!/usr/bin/env python3
"""Debug DuckDuckGo HTML response."""
import urllib.request
import urllib.parse
import re

search_url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote("FIFA World Cup 2026 news")

req = urllib.request.Request(
    search_url,
    headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
)

with urllib.request.urlopen(req, timeout=15) as response:
    html = response.read().decode("utf-8", errors="replace")

# Save full HTML to inspect
with open("/tmp/ddg_output.html", "w") as f:
    f.write(html)

print("HTML saved to /tmp/ddg_output.html")
print(f"Length: {len(html)} bytes")

# Look for any "result" patterns
patterns = [
    r'class="result',
    r'class="result__',
    r'href=".*uddg',
    r'<a[^>]*href="[^"]*"[^>]*>[^<]*[Ww]orld[^<]*[Cc]up',
]

for p in patterns:
    matches = re.findall(p, html)
    print(f"\nPattern: {p}")
    print(f"Matches: {len(matches)}")
    for m in matches[:3]:
        print(f"  -> {m[:200]}")