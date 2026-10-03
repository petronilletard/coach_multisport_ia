import json
import time
import uuid
from datetime import date

import anthropic
from dotenv import load_dotenv

from monitoring import enregistrer
from outils import (activites_recentes, historique, meteo, noter_ressenti,
                    noter_seance, supprimer_seance)

load_dotenv()
client = anthropic.Anthropic()  # lit ANTHROPIC_API_KEY dans l'environnement

# 1. Le menu des outils, décrit pour le LLM
OUTILS = [
    {
        "name": "meteo",
        "description": "Prévisions météo jour par jour pour une ville : températures, "
                       "probabilité de pluie, vent. Utile pour placer course et vélo les jours secs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ville": {"type": "string", "description": "Nom de la ville, ex. Paris"},
                "jours": {"type": "integer", "description": "Nombre de jours de prévision, de 1 à 16"},
            },
            "required": ["ville"],
        },
    },
    {
        "name": "activites_recentes",
        "description": "Activités Strava des derniers jours : natation, course, vélo, entraînements. "
                       "Le vélo d'intérieur a 0 km, la fréquence cardiaque peut manquer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "jours": {"type": "integer", "description": "Nombre de jours à remonter"},
            },
        },
    },
    {
        "name": "noter_seance",
        "description": "Enregistre un entraînement que Strava ne capte pas bien (salle, Pilates), "
                       "avec éventuellement le ressenti pendant la séance. "
                       "Pas pour l'état général sans séance : utiliser noter_ressenti.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "Ex. Pilates, Salle, Natation"},
                "duree_min": {"type": "integer"},
                "ressenti": {"type": "string", "description": "Fatigue, énergie, douleurs…"},
                "jour": {"type": "string", "description": "Format AAAA-MM-JJ, aujourd'hui par défaut"},
            },
            "required": ["type", "duree_min"],
        },
    },
    {
        "name": "historique",
        "description": "Séances notées à la main (avec leur id) et ressentis "
                       "(état général) des dernières semaines.",
        "input_schema": {
            "type": "object",
            "properties": {
                "semaines": {"type": "integer", "description": "Nombre de semaines à remonter"},
            },
        },
    },
    {
        "name": "noter_ressenti",
        "description": "Enregistre mon état général, sans séance : malade, fatiguée, "
                       "en forme, douleur…",
        "input_schema": {
            "type": "object",
            "properties": {
                "etat": {"type": "string", "description": "Ex. malade avec de la fièvre"},
                "jour": {"type": "string", "description": "Format AAAA-MM-JJ, aujourd'hui par défaut"},
            },
            "required": ["etat"],
        },
    },
    {
        "name": "supprimer_seance",
        "description": "Annule une séance notée à la main, à partir de son id (voir historique). "
                       "Ne l'appelle QU'APRÈS m'avoir montré la séance et obtenu mon accord "
                       "explicite dans un message précédent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "L'id de la séance, donné par historique"},
            },
            "required": ["id"],
        },
    },
]

# 2. Le lien entre le nom d'un outil et la vraie fonction Python
FONCTIONS = {
    "meteo": meteo,
    "activites_recentes": activites_recentes,
    "noter_seance": noter_seance,
    "historique": historique,
    "noter_ressenti": noter_ressenti,
    "supprimer_seance": supprimer_seance,
}

SYSTEME = (
    f"Tu es mon coach multisport. Nous sommes le {date.today().isoformat()} et je vis à Paris. "
    "Je fais de la natation, de la course, du vélo, de la salle et du Pilates. "
    "Utilise tes outils pour t'appuyer sur mes vraies données avant de répondre."
)


def executer_outil(nom: str, arguments: dict) -> tuple[str, str | None]:
    """Exécute l'outil demandé par le LLM.
    Renvoie le résultat en texte, et le message d'erreur éventuel (sinon None)."""
    try:
        resultat = FONCTIONS[nom](**arguments)
        erreur = None
    except Exception as e:
        resultat = f"Erreur : {e}"
        erreur = f"{nom} : {e}"
    return json.dumps(resultat, ensure_ascii=False), erreur


# 3. La boucle d'agent
def agent(messages: list, max_tours: int = 10) -> str:

    with open("prompt_coach.md", encoding="utf-8") as f:
        SYSTEME = f"Nous sommes le {date.today().isoformat()}.\n\n" + f.read()

    demande = uuid.uuid4().hex[:8]  # identifiant de cette demande, pour regrouper ses appels

    for tour in range(1, max_tours + 1):
        debut = time.perf_counter()
        reponse = client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=4000,
            system=SYSTEME,
            tools=OUTILS,
            messages=messages,
        )
        duree = time.perf_counter() - debut
        messages.append({"role": "assistant", "content": reponse.content})

        # Le LLM n'a plus besoin d'outils : c'est sa réponse finale
        if reponse.stop_reason != "tool_use":
            enregistrer(demande, tour, duree, reponse, outils=[], erreurs=[])
            texte = "".join(b.text for b in reponse.content if b.type == "text").strip()
            if not texte:
                # Réponse vide : on dit pourquoi au lieu de renvoyer du vide
                print(f"⚠️ Réponse vide, stop_reason = {reponse.stop_reason}")
                return f"Je n'ai pas réussi à rédiger ma réponse (raison : {reponse.stop_reason}). Réessaie."
            return texte

        # Sinon, on exécute chaque outil demandé et on lui renvoie les résultats
        resultats, outils_appeles, erreurs = [], [], []
        for bloc in reponse.content:
            if bloc.type == "tool_use":
                print(f"🔧 {bloc.name}({bloc.input})")
                contenu, erreur = executer_outil(bloc.name, bloc.input)
                outils_appeles.append(bloc.name)
                if erreur:
                    erreurs.append(erreur)
                resultats.append({
                    "type": "tool_result",
                    "tool_use_id": bloc.id,
                    "content": contenu,
                })
        messages.append({"role": "user", "content": resultats})
        enregistrer(demande, tour, duree, reponse, outils_appeles, erreurs)

    return "Je me suis arrêté : trop d'étapes."


if __name__ == "__main__":
    messages = []
    print("Coach prêt ! Écris ton message (ou 'stop' pour quitter).\n")

    while True:
        texte = input("Toi : ").strip()
        if texte.lower() in ("stop", "quit", "exit"):
            break
        if not texte:
            continue

        messages.append({"role": "user", "content": texte})
        print("\nCoach :", agent(messages), "\n")