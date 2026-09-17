"""
Teste rápido de troca de client_credentials (quando aplicável).

Uso:
    python -m src.auth.get_token
Requer: RD_CLIENT_ID, RD_CLIENT_SECRET no ambiente/.env
"""
import os
import sys
import requests
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CLIENT_ID = os.getenv("RD_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("RD_CLIENT_SECRET", "")

if not CLIENT_ID or not CLIENT_SECRET:
    print("[X] Defina RD_CLIENT_ID e RD_CLIENT_SECRET")
    sys.exit(1)

url = os.getenv("OAUTH_TOKEN_URL", "https://api.exemplo.com/oauth/token")
data = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
response = requests.post(url, json=data)
print(response.status_code)
print(response.text)
