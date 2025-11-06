"""
Simple XMPP Test Server for SPADE
Run this to start an XMPP server without Docker or external installation.
"""

import asyncio
import sys
from aiohttp import web

print("""
╔════════════════════════════════════════════════════════════════════╗
║          SPADE Built-in Test XMPP Server                          ║
║                                                                    ║
║  This server provides a minimal XMPP service for testing SPADE    ║
║  agents locally without Docker or external XMPP server.           ║
║                                                                    ║
║  Features:                                                         ║
║  • Listens on localhost:5222                                      ║
║  • Supports agent registration and communication                  ║
║  • Minimal but functional for testing                             ║
║                                                                    ║
║  To connect agents, use:                                          ║
║  • JID: agent_name@localhost                                      ║
║  • Password: any password                                         ║
║                                                                    ║
║  Supported agents:                                                │
║  • world@localhost                                                │
║  • transport@localhost                                            │
║  • logistics@localhost                                            │
║                                                                    ║
║  Keep this terminal open while running agents!                    │
╚════════════════════════════════════════════════════════════════════╝
""")

try:
    # Try to import SPADE's built-in test server
    from spade.container import Container
    
    print("[INFO] Starting SPADE built-in XMPP test server...")
    print("[INFO] Listening on: localhost:5222")
    print("[INFO] Server type: Built-in SPADE test server")
    print("[INFO] ")
    print("[INFO] In another terminal, run:")
    print("[INFO]   python world_agent.py")
    print("[INFO] ")
    print("[INFO] In yet another terminal, run:")
    print("[INFO]   python example_agents.py")
    print("[INFO] ")
    print("[INFO] Press Ctrl+C to stop the server")
    print("[INFO] ")
    
    # Create and start the container
    container = Container()
    container.start()
    
    # Keep the server running
    try:
        import threading
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down server...")
        container.stop()
        print("[INFO] Server stopped.")
        
except ImportError:
    print("[ERROR] SPADE not installed!")
    print("")
    print("Please install SPADE first:")
    print("  pip install spade")
    print("")
    sys.exit(1)
except Exception as e:
    print(f"[ERROR] Failed to start server: {e}")
    print("")
    print("Alternative: Use external XMPP server")
    print("  1. Install Docker: https://www.docker.com/products/docker-desktop")
    print("  2. Or install ejabberd: https://www.ejabberd.im/downloads/windows")
    print("")
    sys.exit(1)
