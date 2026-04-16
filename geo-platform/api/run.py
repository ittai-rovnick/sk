"""
Entry point for the Geo Platform API.
Sets WindowsSelectorEventLoopPolicy BEFORE uvicorn creates its event loop,
which is required for psycopg3 async to work on Windows.
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
