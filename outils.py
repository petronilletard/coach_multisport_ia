import json
import os
import time
import requests
import sqlite3
from datetime import date, timedelta

from dotenv import load_dotenv
from pathlib import Path

DONNEES = Path("donnees")

load_dotenv()
def coordonnees(ville: str) -> tuple[float, float]:
    """Renvoie (latitude, longitude) d'une ville."""
    r = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": ville, "count": 1, "language": "fr"},
        timeout=10,
    )
    r.raise_for_status()
    resultats = r.json().get("results")
    if not resultats:
        raise ValueError(f"Ville introuvable : {ville}")
    return resultats[0]["latitude"], resultats[0]["longitude"]


#timeout=10 évite que ton programme attende indéfiniment si l'API ne répond pas.

def meteo(ville: str, jours: int = 7) -> list[dict]:
    """Prévisions météo jour par jour pour une ville.
    Utile pour placer les séances en extérieur (course, vélo) les jours secs."""
    lat, lon = coordonnees(ville)
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_min,temperature_2m_max,"
                     "precipitation_probability_max,wind_speed_10m_max",
            "timezone": "Europe/Paris",
            "forecast_days": jours,
        },
        timeout=10,
    )
    r.raise_for_status()
    d = r.json()["daily"]

    previsions = []
    for i in range(len(d["time"])):
        previsions.append({
            "date": d["time"][i],
            "temp_min": d["temperature_2m_min"][i],
            "temp_max": d["temperature_2m_max"][i],
            "proba_pluie_%": d["precipitation_probability_max"][i],
            "vent_max_kmh": d["wind_speed_10m_max"][i],
        })
    return previsions

def token_strava() -> str:
    """Renvoie un access token Strava valide, en le renouvelant si besoin."""
    with open("DONNEES/tokens.json") as f:
        tokens = json.load(f)

    # Encore valable plus d'une minute ? On le garde.
    if tokens["expires_at"] > time.time() + 60:
        return tokens["access_token"]

    # Sinon, on en demande un nouveau avec le refresh token.
    r = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": os.environ["STRAVA_CLIENT_ID"],
            "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
        },
        timeout=10,
    )
    r.raise_for_status()
    nouveau = r.json()

    tokens = {
        "access_token": nouveau["access_token"],
        "refresh_token": nouveau["refresh_token"],
        "expires_at": nouveau["expires_at"],
    }
    with open("tokens.json", "w") as f:
        json.dump(tokens, f, indent=2)
    return tokens["access_token"]

def activites_recentes(jours: int = 7) -> list[dict]:
    """Activités Strava des derniers jours (natation, course, vélo, etc.).
    Utile pour faire le bilan de la semaine et repérer la fatigue."""
    depuis = int(time.time()) - jours * 24 * 3600

    r = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers={"Authorization": f"Bearer {token_strava()}"},
        params={"after": depuis, "per_page": 100},
        timeout=10,
    )
    r.raise_for_status()

    activites = []
    for a in r.json():
        activites.append({
            "date": a["start_date_local"][:10],
            "sport": a["sport_type"],
            "nom": a["name"],
            "distance_km": round(a["distance"] / 1000, 2),
            "duree_min": round(a["moving_time"] / 60),
            "denivele_m": a.get("total_elevation_gain"),
            "fc_moyenne": a.get("average_heartrate"),
        })
    return activites

def connexion() -> sqlite3.Connection:
    """Ouvre la base et crée la table des séances si elle n'existe pas encore."""
    conn = sqlite3.connect("DONNEES/coach.db")
    conn.row_factory = sqlite3.Row  # pour lire les lignes comme des dictionnaires
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seances (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            date      TEXT NOT NULL,
            type      TEXT NOT NULL,
            duree_min INTEGER NOT NULL,
            ressenti  TEXT
        )
    """)
    return conn

def noter_seance(type: str, duree_min: int, ressenti: str = "", jour: str = "") -> str:
    """Enregistre une séance que Strava ne capte pas bien (salle, Pilates…)
    ou le ressenti d'une séance. jour au format AAAA-MM-JJ, aujourd'hui par défaut."""
    if duree_min <= 0:
        raise ValueError("La durée doit être positive.")
    jour = jour or date.today().isoformat()

    with connexion() as conn:
        conn.execute(
            "INSERT INTO seances (date, type, duree_min, ressenti) VALUES (?, ?, ?, ?)",
            (jour, type, duree_min, ressenti),
        )
    return f"Séance enregistrée : {type}, {duree_min} min, le {jour}."

def historique(semaines: int = 4) -> list[dict]:
    """Séances notées à la main sur les dernières semaines (salle, Pilates, ressenti)."""
    depuis = (date.today() - timedelta(weeks=semaines)).isoformat()

    with connexion() as conn:
        lignes = conn.execute(
            "SELECT date, type, duree_min, ressenti FROM seances "
            "WHERE date >= ? ORDER BY date",
            (depuis,),
        ).fetchall()
    return [dict(l) for l in lignes]

if __name__ == "__main__":
    print(noter_seance("Pilates", 45, "un peu fatiguée", "2026-09-26"))
    print(noter_seance("Salle", 60, "bonne énergie"))
    for s in historique(2):
        print(s)