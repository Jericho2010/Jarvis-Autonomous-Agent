#!/usr/bin/env python3
import os
import sys
from pathlib import Path

def main():
    print("=== J.A.R.V.I.S. Playwright Verification ===")
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FAIL] Python package 'playwright' is not installed.", file=sys.stderr)
        print("Please run: uv pip install playwright or pip install playwright", file=sys.stderr)
        sys.exit(1)
        
    print("[INFO] Playwright package imported successfully.")
    
    # Ensure webvision dir exists
    webvision_dir = Path("/home/shaun/jarvis/webvision")
    webvision_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = webvision_dir / "verify_screenshot.png"
    
    try:
        with sync_playwright() as p:
            print("[INFO] Launching Chromium browser (headless)...")
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            url = "https://example.com"
            print(f"[INFO] Navigating to {url}...")
            page.goto(url)
            
            title = page.title()
            print(f"[INFO] Page Title: '{title}'")
            
            if "Example Domain" in title:
                print("[PASS] Successfully loaded example.com content.")
            else:
                print(f"[WARN] Loaded page but title does not match. Got: '{title}'")
                
            print(f"[INFO] Saving screenshot to {screenshot_path}...")
            page.screenshot(path=str(screenshot_path))
            print(f"[PASS] Screenshot saved successfully ({screenshot_path.stat().st_size} bytes).")
            
            browser.close()
            print("[PASS] Browser shut down cleanly.")
            print("[SUCCESS] Playwright integration is fully operational.")
            sys.exit(0)
    except Exception as e:
        print(f"[FAIL] Playwright execution failed: {e}", file=sys.stderr)
        print("If browsers are missing, try running: playwright install", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
