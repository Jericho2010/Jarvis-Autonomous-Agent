#!/usr/bin/env python3
import shutil
import sys

def main():
    print("=== J.A.R.V.I.S. OS Dependency Verification ===")
    
    dependencies = ["xdotool", "scrot", "wmctrl"]
    missing = []
    
    for cmd in dependencies:
        path = shutil.which(cmd)
        if path:
            print(f"[PASS] {cmd} found at: {path}")
        else:
            print(f"[FAIL] {cmd} is missing from the system PATH.")
            missing.append(cmd)
            
    if missing:
        print("\n[FAIL] OS dependencies check failed.", file=sys.stderr)
        print(f"Please run the following command to install them:\n", file=sys.stderr)
        print(f"  sudo apt install {' '.join(missing)}\n", file=sys.stderr)
        sys.exit(1)
        
    print("\n[SUCCESS] All OS dependencies (xdotool, scrot, wmctrl) are installed and available in PATH.")
    sys.exit(0)

if __name__ == "__main__":
    main()
