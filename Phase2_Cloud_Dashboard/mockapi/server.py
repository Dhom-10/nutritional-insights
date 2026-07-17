import http.server, socketserver, json, urllib.parse, os, sys

DATA_DIR = "/sessions/quirky-gracious-darwin/mnt/outputs/_inspect/nutritional-insights"
sys.path.insert(0, "/sessions/quirky-gracious-darwin/mnt/outputs/Phase2_Cloud_Dashboard/azure-function")
import pandas as pd
import function_app as fa

df_full = pd.read_csv(os.path.join(DATA_DIR, "All_Diets.csv"), usecols=fa.NEEDED_COLUMNS)
df_full = fa._clean(df_full)

class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/api/insights":
            diet = qs.get("diet_type", [None])[0]
            try:
                result = fa._analyze(df_full.copy(), diet)
                result["execution_time_ms"] = 12.3
                result["diet_filter_applied"] = diet or "all"
                self._send(result)
            except ValueError as e:
                self._send({"error": str(e)}, 404)
        elif parsed.path == "/api/diet_types":
            self._send({"diet_types": sorted(df_full["Diet_type"].unique().tolist())})
        else:
            self.send_response(404); self.end_headers()

    def log_message(self, *args):
        pass

with socketserver.TCPServer(("", 7071), Handler) as httpd:
    httpd.serve_forever()
