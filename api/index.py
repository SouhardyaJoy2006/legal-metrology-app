"""
Vercel serverless entrypoint.

This does not contain any application logic — it just makes the existing
Flask app (defined in ../main.py) importable and discoverable by Vercel's
Python runtime, which looks for a WSGI-compatible `app` object in
api/index.py.
"""
import os
import sys

# main.py does `from form import ...` / `from ai_services import ...`
# (imports relative to the Integration/ folder), so that folder needs to be
# on sys.path before we import it.
INTEGRATION_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if INTEGRATION_DIR not in sys.path:
    sys.path.insert(0, INTEGRATION_DIR)

os.environ.setdefault("VERCEL", "1")

from main import app  # noqa: E402  (the actual Flask app, unmodified logic)

# Vercel's Python runtime looks for this name.
app = app
