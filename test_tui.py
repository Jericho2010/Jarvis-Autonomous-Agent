import sys
import os
import asyncio
from pathlib import Path

# Setup paths
sys.path.append("/home/shaun/jarvis/src")
from jarvis.cli import JarvisTUI

async def test():
    tui = JarvisTUI()
    await tui.init()
    print("\n--- Testing /model list ---")
    await tui.handle_slash("/model")
    
    print("\n--- Testing /model 2 (fixed) ---")
    await tui.handle_slash("/model 2")
    print(f"Agent state primary_model: {tui.agent.client.primary_model}")
    
    print("\n--- Testing /model dynamic ---")
    await tui.handle_slash("/model dynamic")
    print(f"Agent state primary_model: {tui.agent.client.primary_model}")
    
    print("\n--- Testing splash print ---")
    tui.print_splash()
    
if __name__ == '__main__':
    asyncio.run(test())
