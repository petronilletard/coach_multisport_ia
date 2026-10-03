import json
import os

import requests
from dotenv import load_dotenv
from pathlib import Path

DONNEES = Path("donnees")

load_dotenv()  # lit ton fichier .env
CLIENT_ID = os.environ["STRAVA_CLIENT_ID"]
CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]

# Temps 1 : le lien d'autorisation
url = (
    "https://www.strava.com/oauth/authorize"
    f"?client_id={CLIENT_ID}"
    "&response_type=code"
    "&redirect_uri=http://localhost"
    "&approval_prompt=force"
    "&scope=read,activity:read_all"
)
print("1. Ouvre ce lien dans ton navigateur et clique sur Autoriser :\n")
print(url)

# Temps 2 : tu récupères le code
code = input("\n2. Colle ici le code trouvé dans l'URL : ").strip()

# Temps 3 : échange du code contre les jetons
r = requests.post(
    "https://www.strava.com/oauth/token",
    data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
    },
    timeout=10,
)
r.raise_for_status()
reponse = r.json()

tokens = {
    "access_token": reponse["access_token"],
    "refresh_token": reponse["refresh_token"],
    "expires_at": reponse["expires_at"],
}
with open("DONNEES/tokens.json", "w") as f:
    json.dump(tokens, f, indent=2)

print(f"\n✅ Connectée en tant que {reponse['athlete']['firstname']} ! Jetons enregistrés.")