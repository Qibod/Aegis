#!/bin/sh
# Start a minimal HTTP health server alongside the Celery worker.
# Railway requires an HTTP healthcheck; this satisfies it without a full web stack.
python3 -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import os

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{\"status\":\"ok\"}')
    def log_message(self, *args):
        pass

port = int(os.environ.get('PORT', 8000))
HTTPServer(('', port), HealthHandler).serve_forever()
" &

exec celery -A app.workers.tasks.celery_app worker \
    --beat --loglevel=info --concurrency=2
