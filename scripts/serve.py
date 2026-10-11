#!/usr/bin/env python3
"""pet-event 폴더를 로컬에서 서빙한다:  python3 scripts/serve.py [port]"""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
port = int(sys.argv[1]) if len(sys.argv) > 1 else 5180
print("http://localhost:%d  (%s)" % (port, ROOT), flush=True)
ThreadingHTTPServer(("127.0.0.1", port), partial(SimpleHTTPRequestHandler, directory=str(ROOT))).serve_forever()
