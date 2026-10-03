"""Monitoring léger : une ligne par appel au LLM, enregistrée dans coach.db.

Lancer `python monitoring.py` affiche le résumé des 7 derniers jours
(`python monitoring.py 30` pour les 30 derniers jours).
"""
import sys
from datetime import datetime, timedelta

from outils import connexion

# Prix de Claude Sonnet 5.5, en dollars par million de tokens.
# Source : page des prix d'Anthropic (à revérifier si le modèle ou les prix changent).
PRIX_ENTREE = 2.0
PRIX_SORTIE = 10.0


def _creer_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS appels_llm (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            horodatage    TEXT NOT NULL,
            demande       TEXT NOT NULL,
            tour          INTEGER NOT NULL,
            duree_s       REAL NOT NULL,
            tokens_entree INTEGER NOT NULL,
            tokens_sortie INTEGER NOT NULL,
            cout_usd      REAL NOT NULL,
            stop_reason   TEXT,
            outils        TEXT,
            erreurs       TEXT
        )
    """)


def enregistrer(demande: str, tour: int, duree_s: float, reponse, outils: list, erreurs: list):
    """Enregistre un appel au LLM. Ne fait jamais planter l'agent."""
    try:
        entree = reponse.usage.input_tokens
        sortie = reponse.usage.output_tokens
        cout = entree / 1_000_000 * PRIX_ENTREE + sortie / 1_000_000 * PRIX_SORTIE
        with connexion() as conn:
            _creer_table(conn)
            conn.execute(
                "INSERT INTO appels_llm (horodatage, demande, tour, duree_s, tokens_entree, "
                "tokens_sortie, cout_usd, stop_reason, outils, erreurs) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now().isoformat(timespec="seconds"),
                    demande,
                    tour,
                    round(duree_s, 2),
                    entree,
                    sortie,
                    cout,
                    reponse.stop_reason,
                    ",".join(outils),
                    " | ".join(erreurs),
                ),
            )
    except Exception as e:
        # Le monitoring ne doit jamais casser le coach : on prévient et on continue.
        print(f"⚠️ Monitoring : enregistrement impossible ({e})")


def resume(jours: int = 7):
    """Affiche un résumé des appels au LLM sur les derniers jours."""
    depuis = (datetime.now() - timedelta(days=jours)).isoformat(timespec="seconds")
    with connexion() as conn:
        _creer_table(conn)
        lignes = [dict(l) for l in conn.execute(
            "SELECT * FROM appels_llm WHERE horodatage >= ? ORDER BY horodatage", (depuis,)
        ).fetchall()]

    if not lignes:
        print(f"Aucun appel au LLM sur les {jours} derniers jours.")
        return

    demandes = {l["demande"] for l in lignes}
    cout = sum(l["cout_usd"] for l in lignes)
    entree = sum(l["tokens_entree"] for l in lignes)
    sortie = sum(l["tokens_sortie"] for l in lignes)
    duree_moy = sum(l["duree_s"] for l in lignes) / len(lignes)

    outils, raisons = {}, {}
    erreurs = []
    for l in lignes:
        for o in filter(None, (l["outils"] or "").split(",")):
            outils[o] = outils.get(o, 0) + 1
        raisons[l["stop_reason"]] = raisons.get(l["stop_reason"], 0) + 1
        if l["erreurs"]:
            erreurs.append(f'{l["horodatage"]} : {l["erreurs"]}')

    print(f"MONITORING DU COACH — {jours} derniers jours")
    print(f"- Demandes : {len(demandes)}, appels au LLM : {len(lignes)} "
          f"({len(lignes) / len(demandes):.1f} par demande)")
    print(f"- Coût : {cout:.3f} $ ({cout / len(demandes):.3f} $ par demande)")
    milliers = lambda n: f"{n:,}".replace(",", " ")  # 13000 -> "13 000"
    print(f"- Tokens : {milliers(entree)} en entrée, {milliers(sortie)} en sortie")
    print(f"- Temps de réponse moyen du LLM : {duree_moy:.1f} s")
    print("- Outils appelés : " + (", ".join(f"{o} ×{n}" for o, n in sorted(outils.items())) or "aucun"))
    print("- Raisons d'arrêt : " + ", ".join(f"{r} ×{n}" for r, n in raisons.items()))
    print(f"- Erreurs d'outils : {len(erreurs)}")
    for e in erreurs[-5:]:
        print(f"    {e}")


if __name__ == "__main__":
    resume(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
