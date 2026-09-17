"""
# Mock API — antes: https://api.exemplo.com — troque via env OAUTH_BASE_URL se necessário

Autenticação RD Station CRM — servidor local (captura automática).

Uso:
    cp .env.example .env
    python -m src.auth.auth_server
    # abre http://localhost:8080/callback automaticamente

Requer: RD_CLIENT_ID, RD_CLIENT_SECRET, RD_REDIRECT_URL=http://localhost:8080/callback
"""
import json
import os
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CLIENT_ID = os.getenv("RD_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("RD_CLIENT_SECRET", "")
REDIRECT_URL = os.getenv("RD_REDIRECT_URL", "http://localhost:8080/callback")

if not CLIENT_ID or not CLIENT_SECRET:
    print("[X] Defina RD_CLIENT_ID e RD_CLIENT_SECRET no .env ou no ambiente")
    sys.exit(1)

OAUTH_DIALOG_URL = os.getenv("OAUTH_DIALOG_URL", "https://api.exemplo.com/oauth/dialog")
OAUTH_TOKEN_URL = os.getenv("OAUTH_TOKEN_URL", "https://api.exemplo.com/oauth/token")

auth_url = (
    f"{OAUTH_DIALOG_URL}"
    f"?client_id={CLIENT_ID}"
    f"&redirect_url={REDIRECT_URL}"
)

received_code = None

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global received_code
        from urllib.parse import urlparse, parse_qs
        params = parse_qs(urlparse(self.path).query)
        received_code = params.get("code", [None])[0]
        if received_code:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>OK! Pode fechar esta aba.</h1>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h1>Erro: codigo nao encontrado</h1>")
    def log_message(self, format, *args):
        return

server = HTTPServer(("localhost", 8080), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

print("=" * 60)
print("AUTENTICAÇÃO RD STATION CRM (servidor local)")
print("=" * 60)
print("\n1. Abra este link no seu navegador:")
print(f"\n   {auth_url}\n")
print("2. Faça login e autorize o aplicativo")
print("3. O servidor local vai capturar o código automaticamente\n")

try:
    import webbrowser
    webbrowser.open(auth_url)
except Exception:
    pass

timeout = 120
for _ in range(timeout * 2):
    if received_code:
        break
    time.sleep(0.5)

server.shutdown()

if not received_code:
    print("[X] Tempo esgotado. Nenhum código recebido.")
    sys.exit(1)

print("\n[✓] Código obtido!")

data = {
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "code": received_code,
    "redirect_url": REDIRECT_URL,
}

response = requests.post(OAUTH_TOKEN_URL, json=data)

if response.status_code != 200:
    print(f"[X] Erro ao obter token: {response.status_code}")
    print(response.text)
    sys.exit(1)

tokens = response.json()

print("\n[✓] Token obtido com sucesso!")
print(f"    access_token:  {tokens.get('access_token', '')[:60]}...")
print(f"    refresh_token: {tokens.get('refresh_token', '')[:60]}...")

out = os.path.expanduser("~/.rdstation_tokens.json")
with open(out, "w") as f:
    json.dump(tokens, f, indent=2)
print(f"\n[✓] Tokens salvos em {out}")
