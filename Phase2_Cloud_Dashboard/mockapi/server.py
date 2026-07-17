"""
Local mock server for testing the dashboard against function_app.py's logic
without needing a real Azure Function / Blob Storage connection.

Usage:
    python mockapi/server.py [path/to/All_Diets.csv]

If no path is given, it looks for All_Diets.csv next to this script, then
falls back to the DIETS_CSV_PATH environment variable.
Serves on http://localhost:7071/api/... — matches the routes the real
Azure Function exposes, so dashboard/index.html can point its
API_BASE_URL at this server for local testing (no Azure needed).
"""
import http.server
import json
import os
import socketserver
import sys
import urllib.parse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FUNCTION_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "azure-function")
sys.path.insert(0, FUNCTION_DIR)

import pandas as pd  # noqa: E402
import function_app as fa  # noqa: E402

csv_path = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.environ.get("DIETS_CSV_PATH", os.path.join(SCRIPT_DIR, "All_Diets.csv"))
)
if not os.path.exists(csv_path):
    sys.exit(
        f"Could not find dataset CSV at '{csv_path}'.\n"
        "Pass a path explicitly: python mockapi/server.py path/to/All_Diets.csv"
    )

df_full = pd.read_csv(csv_path, usecols=fa.NEEDED_COLUMNS)
df_full = fa._clean(df_full)
print(f"Loaded {len(df_full)} rows from {csv_path}")


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        diet = qs.get("diet_type", [None])[0]

        try:
            if parsed.path == "/api/insights":
                result = fa._analyze(df_full.copy(), diet)
                result["execution_time_ms"] = 12.3
                result["diet_filter_applied"] = diet or "all"
                self._send(result)

            elif parsed.path == "/api/diet_types":
                self._send({"diet_types": sorted(df_full["Diet_type"].unique().tolist())})

            elif parsed.path == "/api/correlations":
                result = fa._correlations(df_full.copy(), diet)
                result["execution_time_ms"] = 4.1
                result["diet_filter_applied"] = diet or "all"
                self._send(result)

            elif parsed.path == "/api/recipes":
                page = int(qs.get("page", [1])[0])
                page_size = int(qs.get("page_size", [10])[0])
                result = fa._paginate_recipes(df_full.copy(), diet, page, page_size)
                result["execution_time_ms"] = 6.7
                result["diet_filter_applied"] = diet or "all"
                self._send(result)

            elif parsed.path == "/api/clusters":
                k = int(qs.get("k", [4])[0])
                result = fa._cluster(df_full.copy(), diet, k)
                result["execution_time_ms"] = 45.2
                result["diet_filter_applied"] = diet or "all"
                self._send(result)

            else:
                self.send_response(404)
                self.end_headers()

        except ValueError as e:
            self._send({"error": str(e)}, 404)
        except Exception as e:
            self._send({"error": f"Internal error: {e}"}, 500)

    def log_message(self, *args):
        pass


with socketserver.TCPServer(("", 7071), Handler) as httpd:
    print("Mock API serving on http://localhost:7071/api/...")
    httpd.serve_forever()
