import json
from datetime import date

import anthropic
from dotenv import load_dotenv

from outils import activites_recentes, historique, meteo, noter_seance

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
        "description": "Enregistre une séance que Strava ne capte pas bien (salle, Pilates) "
                       "ou le ressenti d'une séance.",
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
        "description": "Séances notées à la main sur les dernières semaines (salle, Pilates, ressenti).",
        "input_schema": {
            "type": "object",
            "properties": {
                "semaines": {"type": "integer", "description": "Nombre de semaines à remonter"},
            },
        },
    },
]

# 2. Le lien entre le nom d'un outil et la vraie fonction Python
FONCTIONS = {
    "meteo": meteo,
    "activites_recentes": activites_recentes,
    "noter_seance": noter_seance,
    "historique": historique,
}

SYSTEME = (
    f"Tu es mon coach multisport. Nous sommes le {date.today().isoformat()} et je vis à Paris. "
    "Je fais de la natation, de la course, du vélo, de la salle et du Pilates. "
    "Utilise tes outils pour t'appuyer sur mes vraies données avant de répondre."
)


def executer_outil(nom: str, arguments: dict) -> str:
    """Exécute l'outil demandé par le LLM et renvoie le résultat en texte."""
    try:
        resultat = FONCTIONS[nom](**arguments)
    except Exception as e:
        resultat = f"Erreur : {e}"
    return json.dumps(resultat, ensure_ascii=False)


# 3. La boucle d'agent
def agent(messages: list, max_tours: int = 10) -> str:

    with open("prompt_coach.md", encoding="utf-8") as f:
        SYSTEME = f"Nous sommes le {date.today().isoformat()}.\n\n" + f.read()

    for _ in range(max_tours):
        reponse = client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=2000,
            system=SYSTEME,
            tools=OUTILS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": reponse.content})

        # Le LLM n'a plus besoin d'outils : c'est sa réponse finale
        if reponse.stop_reason != "tool_use":
            return "".join(b.text for b in reponse.content if b.type == "text")

        # Sinon, on exécute chaque outil demandé et on lui renvoie les résultats
        resultats = []
        for bloc in reponse.content:
            if bloc.type == "tool_use":
                print(f"🔧 {bloc.name}({bloc.input})")
                resultats.append({
                    "type": "tool_result",
                    "tool_use_id": bloc.id,
                    "content": executer_outil(bloc.name, bloc.input),
                })
        messages.append({"role": "user", "content": resultats})

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