#!/usr/bin/env python3
"""
Search for current FIFA World Cup news using DuckDuckGo.
"""
import urllib.request
import urllib.parse
import re
from html import unescape

def web_search(query: str, max_results: int = 10) -> list:
    """Search the web using DuckDuckGo HTML and extract real URLs."""
    search_url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    
    req = urllib.request.Request(
        search_url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )
    
    with urllib.request.urlopen(req, timeout=15) as response:
        html = response.read().decode("utf-8")
    
    # DuckDuckGo HTML wraps links in redirect URLs.
    # Pattern: class="result__a" href="//duckduckgo.com/l/?uddg=..."
    pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
    matches = re.findall(pattern, html, re.DOTALL)
    
    results = []
    for href, title in matches[:max_results]:
        title = re.sub(r'<[^>]+>', '', title)
        title = unescape(title)
        
        # Extract the real URL from DuckDuckGo redirect
        if "uddg=" in href:
            # Extract the uddg parameter
            match = re.search(r'uddg=([^&]+)', href)
            if match:
                real_url = urllib.parse.unquote(match.group(1))
            else:
                real_url = href
        else:
            real_url = href
        
        if real_url.startswith("http"):
            results.append({"title": title.strip(), "url": real_url})
    
    return results

def fetch_page_text(url: str) -> str:
    """Fetch a web page and return cleaned text."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )
    
    with urllib.request.urlopen(req, timeout=15) as response:
        html = response.read().decode("utf-8", errors="replace")
    
    # Remove script and style
    text = re.sub(r'(?is)<(script|style)\b[^>]*>[\s\S]*?</\1>', '', html)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text[:5000]

def extract_sentences(text: str, max_sentences: int = 6) -> str:
    """Extract first N sentences."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return " ".join(sentences[:max_sentences])

if __name__ == "__main__":
    queries = [
        "FIFA World Cup 2026 news latest",
        "World Cup 2026 qualifiers results",
        "FIFA World Cup 2026 host cities stadiums",
        "World Cup 2026 tickets teams"
    ]
    
    all_results = []
    for q in queries:
        print(f"Searching: {q}", flush=True)
        try:
            results = web_search(q, max_results=5)
            for r in results:
                all_results.append(r)
        except Exception as e:
            print(f"  Error: {e}")
    
    # Deduplicate
    seen = set()
    unique = []
    for r in all_results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)
    
    print(f"\n{'='*70}")
    print(f"FIFA WORLD CUP 2026 - TOP STORIES & NEWS REPORT")
    print(f"{'='*70}\n")
    
    count = 0
    for i, r in enumerate(unique):
        if count >= 8:
            break
        
        print(f"STORY {count+1}: {r['title']}")
        print(f"Source: {r['url']}")
        
        try:
            text = fetch_page_text(r["url"])
            summary = extract_sentences(text, max_sentences=4)
            print(f"Summary: {summary}")
        except Exception as e:
            print(f"Could not fetch: {e}")
        
        print("-" * 70)
        count += 1