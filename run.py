#!/usr/bin/env python3
"""Launch the Intent Analyzer dashboard."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=5001,
        reload=True,
        reload_excludes=[".venv", "__pycache__", "data"],
    )
