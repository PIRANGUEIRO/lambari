"""
# Mock API — antes: https://api.exemplo.com — troque via env OAUTH_BASE_URL se necessário

Autenticação RD Station CRM — fluxo manual (copiar URL de callback).

Uso:
    cp .env.example .env
    # preencha RD_CLIENT_ID e RD_CLIENT_SECRET no .env
    pip install -r requirements.txt
    python -m src.auth.auth

Requer variáveis de ambiente:
    RD_CLIENT_ID, RD_CLIENT_SECRET, RD_REDIRECT_URL
"""
import json
import os
import sys
from urllib.parse import urlparse, parse_qs

import requests
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CLIENT_ID = os.getenv("RD_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("RD_CLIENT_SECRET", "")
REDIRECT_URL = os.getenv("RD_REDIRECT_URL", "https://exemplo.com/callback")

if not CLIENT_ID or not CLIENT_SECRET:
    print("[X] Defina RD_CLIENT_ID e RD_CLIENT_SECRET no .env ou no ambiente")
    print("    cp .env.example .env  # e edite")
    sys.exit(1)

OAUTH_DIALOG_URL = os.getenv("OAUTH_DIALOG_URL", "https://api.exemplo.com/oauth/dialog")
OAUTH_TOKEN_URL = os.getenv("OAUTH_TOKEN_URL", "https://api.exemplo.com/oauth/token")

auth_url = (
    f"{OAUTH_DIALOG_URL}"
    f"?client_id={CLIENT_ID}"
    f"&redirect_url={REDIRECT_URL}"
)

print("=" * 60)
print("AUTENTICAÇÃO RD STATION CRM")
print("=" * 60)
print("\n1. Abra este link no seu navegador:")
print(f"\n   {auth_url}\n")
print("2. Faça login na sua conta RD Station")
print("3. Autorize o aplicativo")
print("4. O navegador vai tentar abrir uma URL tipo:")
print("   https://exemplo.com/callback?code=...")
print("\n5. Copie o link COMPLETO (a URL inteira) que aparecer")
print("   e cole abaixo:\n")

redirect_result = input("URL completa recebida: ").strip()

parsed = urlparse(redirect_result)
params = parse_qs(parsed.query)
code = params.get("code", [None])[0]

if not code:
    print("[X] Código não encontrado na URL")
    sys.exit(1)

print("\n[✓] Código obtido, trocando por token de acesso...")

data = {
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "code": code,
    "redirect_url": REDIRECT_URL,
}

response = requests.post(OAUTH_TOKEN_URL, json=data)

if response.status_code != 200:
    print(f"[X] Erro ao obter token: {response.status_code}")
    print(response.text)
    sys.exit(1)

tokens = response.json()

print("\n[✓] Token obtido com sucesso!")
print(f"    access_token:  {tokens.get('access_token', '')[:50]}...")
print(f"    refresh_token: {tokens.get('refresh_token', '')[:50]}...")

out = os.path.expanduser("~/.rdstation_tokens.json")
with open(out, "w") as f:
    json.dump(tokens, f, indent=2)
print(f"\n[✓] Tokens salvos em {out}")
print("    ATENÇÃO: este arquivo contém segredo — não commitar")
