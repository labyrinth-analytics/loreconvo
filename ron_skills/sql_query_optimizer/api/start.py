"""Startup script that reads PORT from environment and launches uvicorn."""
import os
import uvicorn

port = int(os.environ.get("PORT", "8000"))
print(f"Starting SQL Optimizer API on port {port}")
uvicorn.run("main:app", host="0.0.0.0", port=port)
