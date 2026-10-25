"""
================================================================================
WSGI ENTRYPOINT FOR PRODUCTION SERVERS (Gunicorn / Waitress / uWSGI)
================================================================================
Usage:
    Linux / Cloud:
        gunicorn --bind 0.0.0.0:5000 wsgi:app

    Windows Production:
        waitress-serve --listen=0.0.0.0:5000 wsgi:app
================================================================================
"""

import os
import sys

# Ensure current directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import app

# Expose both 'app' and 'application' aliases for various WSGI runners
application = app

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    app.run(host=host, port=port)
