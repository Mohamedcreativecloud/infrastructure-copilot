import os
import sys
import asyncio

# Ensure the project root is on the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_root)
sys.path.insert(0, project_root)

from mcp_server.server import main

if __name__ == "__main__":
    asyncio.run(main())
