"""Moteur de recherche sémantique et pipeline RAG (étape 5).

    question
      → vecteur (même modèle d'embedding que l'indexation)
      → similarité cosinus avec tous les segments de la base → Top-K segments
      → seuil de pertinence : si rien n'est assez proche, réponse « je ne sais pas » sans appeler le LLM
      → prompt strict : contexte numéroté [1], [2]… + question
      → LLM local (Ollama) → réponse avec citations [n]
      → réponse + sources (fichier, page ou section, extrait)

Usage en ligne de commande (base déjà indexée avec POST /index) :
    python -m src.rag "Combien de fois par semaine faut-il manger du poisson ?"
    python -m src.rag --validation         # pose toutes les questions de validation et les pièges
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Protocol

K_PAR_DEFAUT = 5
# Score cosinus minimal du meilleur segment pour interroger le LLM.
# À calibrer avec la colonne « Piège » de python -m src.evaluate.
SEUIL_PAR_DEFAUT = 0.30

REPONSE_INCONNUE = "Je ne sais pas : cette information n'est pas dans les documents du corpus."

PROMPT_SYSTEME = f"""Tu es l'assistant du projet WebCognitive, spécialisé dans l'alimentation et la nutrition.
À partir uniquement du contexte textuel fourni ci-dessous, réponds précisément à la question de l'utilisateur.

Règles :
1. N'utilise aucune connaissance extérieure au contexte, même si tu crois connaître la réponse.
2. Si la réponse n'est pas dans le contexte, réponds exactement : « {REPONSE_INCONNUE} »
3. Cite la ou les sources utilisées avec leur numéro entre crochets, par exemple [1] ou [2][3], juste après l'information.
4. Reprends les chiffres exactement comme ils sont écrits dans le contexte.
5. Réponds en français, en 2 à 5 phrases, sans donner de conseil médical personnalisé."""


class LLM(Protocol):
    nom: str

    def generer(self, messages: list[dict]) -> str: ...


# --------------------------------------------------------------------- recherche

def fusionner_voisins(segments: list[dict]) -> list[dict]:
    """Fusionne les segments qui se chevauchent dans un même bloc (même document, même page/section).

    Avec le chevauchement de l'étape 3, deux segments voisins répètent quelques phrases :
    on les réunit en une seule source pour ne pas envoyer deux fois le même texte au LLM.
    L'ordre (le plus pertinent d'abord) est conservé.
    """
    fusionnes: list[dict] = []
    for s in segments:
        m = s["metadonnees"]
        cible = next((f for f in fusionnes
                      if f["metadonnees"].get("doc_id") == m.get("doc_id")
                      and f["metadonnees"].get("bloc") == m.get("bloc")
                      and "debut" in m and f["debut"] <= m["fin"] and m["debut"] <= f["fin"]), None)
        if cible is None:
            fusionnes.append({**s, "ids": [s["id"]], "debut": m.get("debut", 0), "fin": m.get("fin", 0)})
            continue
        # Union des deux intervalles [debut, fin] du même bloc : les textes sont des tranches
        # exactes du bloc, on peut donc les recoller sans rien répéter.
        if m["debut"] <= cible["debut"]:
            premier, second = (s["texte"], m["debut"], m["fin"]), (cible["texte"], cible["debut"], cible["fin"])
        else:
            premier, second = (cible["texte"], cible["debut"], cible["fin"]), (s["texte"], m["debut"], m["fin"])
        texte, debut, fin = premier
        if second[2] > fin:  # le second dépasse à droite : on ajoute la partie qui manque
            texte += second[0][fin - second[1]:]
            fin = second[2]
        cible.update(texte=texte, debut=debut, fin=fin)
        cible["ids"].append(s["id"])
        cible["score"] = max(cible["score"], s["score"])
    return fusionnes


def rechercher(question: str, base, encodeur, k: int = K_PAR_DEFAUT, filtre: dict | None = None) -> list[dict]:
    """Top-K : les k segments dont le vecteur est le plus proche (similarité cosinus) de la question."""
    vecteur = encodeur.encoder([question])[0]
    return base.rechercher(vecteur, k, filtre)


# --------------------------------------------------------------------- prompt

def etiquette(meta: dict) -> str:
    """« Le sel — section : Où se cache le sel ? (sel.html) »"""
    morceaux = [meta.get("titre") or meta.get("doc_id", "?")]
    if meta.get("position"):
        morceaux.append(meta["position"])
    nom = Path(meta.get("fichier") or "").name
    return " — ".join(morceaux) + (f" ({nom})" if nom else "")


def construire_messages(question: str, sources: list[dict]) -> list[dict]:
    contexte = "\n\n".join(f"[{i}] {etiquette(s['metadonnees'])}\n{s['texte']}"
                           for i, s in enumerate(sources, start=1))
    return [
        {"role": "system", "content": PROMPT_SYSTEME},
        {"role": "user", "content": f"Contexte :\n\n{contexte}\n\nQuestion : {question}"},
    ]


def numeros_cites(reponse: str, nombre_sources: int) -> list[int]:
    """Numéros de sources cités dans la réponse ([1], [2][3], [1, 2]…), sans doublon."""
    numeros = []
    for groupe in re.findall(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]", reponse):
        for n in re.split(r"\s*[,;]\s*", groupe):
            n = int(n)
            if 1 <= n <= nombre_sources and n not in numeros:
                numeros.append(n)
    return numeros


def est_inconnue(reponse: str) -> bool:
    return bool(re.search(r"je ne sais pas|n'est pas dans (le|les) (contexte|documents|corpus)", reponse, re.I))


# --------------------------------------------------------------------- pipeline

def repondre(question: str, base, encodeur, llm: LLM, k: int = K_PAR_DEFAUT,
             seuil: float = SEUIL_PAR_DEFAUT, filtre: dict | None = None) -> dict:
    debut = time.perf_counter()
    trouves = rechercher(question, base, encodeur, k, filtre)
    duree_recherche = time.perf_counter() - debut
    sources = fusionner_voisins(trouves)

    meilleur = max((s["score"] for s in sources), default=0.0)
    resultat = {
        "question": question,
        "modele_llm": llm.nom,
        "seuil": seuil,
        "meilleur_score": round(meilleur, 4),
    }

    if not sources or meilleur < seuil:
        # Rien d'assez proche dans le corpus : on ne demande rien au LLM (pas de risque d'invention)
        resultat.update(reponse=REPONSE_INCONNUE, hors_corpus=True, llm_appele=False, sources=[],
                        durees_s={"recherche": round(duree_recherche, 2), "generation": 0.0})
        return resultat

    debut = time.perf_counter()
    reponse = llm.generer(construire_messages(question, sources))
    duree_generation = time.perf_counter() - debut
    cites = numeros_cites(reponse, len(sources))
    inconnue = est_inconnue(reponse)

    resultat.update(
        reponse=reponse,
        hors_corpus=inconnue,
        llm_appele=True,
        sources=[{
            "numero": i,
            "citee": i in cites,
            "score": round(s["score"], 4),
            "segments": s["ids"],
            "doc_id": s["metadonnees"].get("doc_id"),
            "titre": s["metadonnees"].get("titre"),
            "fichier": s["metadonnees"].get("fichier"),
            "position": s["metadonnees"].get("position"),
            "auteur": s["metadonnees"].get("auteur"),
            "source": s["metadonnees"].get("source"),
            "extrait": s["texte"],
        } for i, s in enumerate(sources, start=1)],
        durees_s={"recherche": round(duree_recherche, 2), "generation": round(duree_generation, 2)},
    )
    return resultat


# --------------------------------------------------------------------- ligne de commande

def afficher(resultat: dict) -> None:
    print(f"\n❓ {resultat['question']}")
    print(f"💬 {resultat['reponse']}")
    if not resultat["llm_appele"]:
        print(f"   (meilleur score {resultat['meilleur_score']:.2f} < seuil {resultat['seuil']:.2f} : LLM non appelé)")
    for s in resultat["sources"]:
        marque = "★" if s["citee"] else " "
        print(f"   {marque} [{s['numero']}] {s['score']:.2f}  {Path(s['fichier'] or '').name} — {s['position']}")
    d = resultat["durees_s"]
    print(f"   ⏱ recherche {d['recherche']} s, génération {d['generation']} s")


def main(argv: list[str] | None = None) -> int:
    from .embeddings import MODELE_PAR_DEFAUT, EncodeurLocal
    from .evaluate import lire_questions
    from .llm import MODELE_LLM_PAR_DEFAUT, ClientOllama, OllamaIndisponible
    from .vectorstore import BaseChroma

    racine = Path(__file__).resolve().parent.parent
    analyseur = argparse.ArgumentParser(description="Poser une question au corpus (RAG local)")
    analyseur.add_argument("question", nargs="?")
    analyseur.add_argument("--validation", action="store_true", help="poser les questions de validation")
    analyseur.add_argument("-k", type=int, default=K_PAR_DEFAUT)
    analyseur.add_argument("--seuil", type=float, default=SEUIL_PAR_DEFAUT)
    analyseur.add_argument("--llm", default=MODELE_LLM_PAR_DEFAUT, help="modèle Ollama (mistral, llama3.1…)")
    args = analyseur.parse_args(argv)
    if not args.question and not args.validation:
        analyseur.error("donnez une question, ou --validation")

    base = BaseChroma(racine / "data" / "chroma")
    if not base.compter():
        print("La base est vide : lancez d'abord l'indexation (POST /index).")
        return 1
    encodeur = EncodeurLocal(base.reglages().get("modele", MODELE_PAR_DEFAUT))
    llm = ClientOllama(args.llm)

    if args.validation:
        chemin = racine / "docs" / "questions_validation.md"
        _, pieges = lire_questions(chemin)
        # Toutes les questions numérotées du tableau, même sans « Fichier source » renseigné
        toutes = re.findall(r"^\| \d+ \| ([^|]*?\S[^|]*?) \|", chemin.read_text(encoding="utf-8"), re.M)
        a_poser = [(q, False) for q in toutes] + [(p, True) for p in pieges]
    else:
        a_poser = [(args.question, False)]

    try:
        for question, piege in a_poser:
            resultat = repondre(question, base, encodeur, llm, args.k, args.seuil)
            afficher(resultat)
            if piege:
                print("   ✅ piège évité" if resultat["hors_corpus"] else "   ❌ piège : le système a répondu")
    except OllamaIndisponible as erreur:
        print(f"\n✘ {erreur}\n")
        return 1
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
