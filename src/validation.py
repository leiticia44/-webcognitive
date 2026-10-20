"""Étape 8 — Validation finale : rapport des questions de validation.

Pose toutes les questions de docs/questions_validation.md (et les questions pièges)
au pipeline RAG complet, puis écrit :

- docs/rapport_validation.md : rapport lisible, à joindre au rendu et à montrer en soutenance ;
- data/validation.json       : les mêmes résultats en JSON.

Contrôles automatiques pour chaque question :
- le système a-t-il répondu, ou dit « je ne sais pas » ?
- le bon document est-il parmi les sources retrouvées, et parmi les sources citées ?
  (seulement si la colonne « Fichier source » est remplie)
- les chiffres de la réponse attendue se retrouvent-ils dans la réponse ?
Pour les pièges : le système doit répondre qu'il ne sait pas.

La justesse du contenu reste à juger par une personne : le rapport met la réponse
attendue et la réponse obtenue côte à côte, avec une case à cocher.

Usage (base indexée et Ollama lancé) :
    python -m src.validation
    python -m src.validation -k 5 --seuil 0.30 --llm mistral
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from .evaluate import _lignes_tableau, _nom
from .rag import K_PAR_DEFAUT, SEUIL_PAR_DEFAUT, repondre

RACINE = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------- lecture du jeu de test

def lire_jeu(chemin: Path) -> tuple[list[dict], list[dict]]:
    """Toutes les questions numérotées (même sans fichier source) et les questions pièges."""
    texte = chemin.read_text(encoding="utf-8")
    questions = [{
        "numero": r["#"], "question": r["Question"], "attendue": r.get("Réponse attendue", ""),
        "fichier": r.get("Fichier source", "").strip("` "), "position": r.get("Page / section", ""),
    } for r in _lignes_tableau(texte, "| # |") if r.get("Question")]
    pieges = [{"question": r["Question"], "attendu": r.get("Comportement attendu", "")}
              for r in _lignes_tableau(texte, "| Question | Comportement") if r.get("Question")]
    return questions, pieges


def chiffres(texte: str) -> list[str]:
    """Nombres d'un texte, normalisés (« 2,4 » et « 2.4 » sont identiques)."""
    return [n.replace(",", ".") for n in re.findall(r"\d+(?:[.,]\d+)?", texte or "")]


def chiffres_retrouves(attendue: str, reponse: str) -> bool | None:
    """Tous les chiffres de la réponse attendue sont-ils dans la réponse ? None s'il n'y en a pas."""
    attendus = set(chiffres(attendue))
    if not attendus:
        return None
    return attendus <= set(chiffres(reponse))


# --------------------------------------------------------------------- validation

def valider(questions: list[dict], pieges: list[dict], base, encodeur, llm,
            k: int = K_PAR_DEFAUT, seuil: float = SEUIL_PAR_DEFAUT, progression=None) -> dict:
    lignes, lignes_pieges = [], []
    total = len(questions) + len(pieges)
    for rang, q in enumerate(questions, start=1):
        if progression:
            progression(rang, total, q["question"])
        r = repondre(q["question"], base, encodeur, llm, k, seuil)
        fichiers = [_nom(s.get("fichier")) for s in r["sources"]]
        cites = [_nom(s.get("fichier")) for s in r["sources"] if s["citee"]]
        attendu = _nom(q["fichier"]) if q["fichier"] else None
        lignes.append({
            **q,
            "reponse": r["reponse"],
            "a_repondu": not r["hors_corpus"],
            "meilleur_score": r["meilleur_score"],
            "source_retrouvee": (attendu in fichiers) if attendu else None,
            "source_citee": (attendu in cites) if attendu else None,
            "chiffres_retrouves": chiffres_retrouves(q["attendue"], r["reponse"]) if not r["hors_corpus"] else False,
            "sources": [{"numero": s["numero"], "citee": s["citee"], "score": s["score"],
                         "fichier": s.get("fichier"), "position": s.get("position")} for s in r["sources"]],
            "durees_s": r["durees_s"],
        })
    for rang, p in enumerate(pieges, start=len(questions) + 1):
        if progression:
            progression(rang, total, p["question"])
        r = repondre(p["question"], base, encodeur, llm, k, seuil)
        lignes_pieges.append({**p, "reponse": r["reponse"], "evite": r["hors_corpus"],
                              "llm_appele": r["llm_appele"], "meilleur_score": r["meilleur_score"],
                              "durees_s": r["durees_s"]})

    avec_source = [l for l in lignes if l["source_retrouvee"] is not None]
    avec_chiffres = [l for l in lignes if l["chiffres_retrouves"] is not None]
    generations = [l["durees_s"]["generation"] for l in lignes + lignes_pieges if l["durees_s"]["generation"]]
    return {
        "date": datetime.now().isoformat(timespec="seconds"),
        "reglages": {"k": k, "seuil": seuil, "modele_llm": getattr(llm, "nom", "?"),
                     "modele_embedding": base.reglages().get("modele"),
                     "taille": base.reglages().get("taille"), "chevauchement": base.reglages().get("chevauchement"),
                     "segments_en_base": base.compter()},
        "resume": {
            "questions": len(lignes),
            "repondues": sum(l["a_repondu"] for l in lignes),
            "questions_avec_source": len(avec_source),
            "source_retrouvee": sum(bool(l["source_retrouvee"]) for l in avec_source),
            "source_citee": sum(bool(l["source_citee"]) for l in avec_source),
            "questions_avec_chiffres": len(avec_chiffres),
            "chiffres_retrouves": sum(bool(l["chiffres_retrouves"]) for l in avec_chiffres),
            "pieges": len(lignes_pieges),
            "pieges_evites": sum(l["evite"] for l in lignes_pieges),
            "generation_moyenne_s": round(sum(generations) / len(generations), 2) if generations else 0.0,
        },
        "questions": lignes,
        "pieges": lignes_pieges,
    }


# --------------------------------------------------------------------- rapport Markdown

def _oui_non(valeur: bool | None) -> str:
    return "—" if valeur is None else ("✅" if valeur else "❌")


def _cellule(texte: str) -> str:
    return re.sub(r"\s+", " ", (texte or "").replace("|", "\\|")).strip()


def rapport_markdown(resultats: dict) -> str:
    r, g = resultats["resume"], resultats["reglages"]
    modele = str(g.get("modele_embedding") or "?").split("/")[-1]
    lignes = [
        "# Rapport de validation — WebCognitive Engine",
        "",
        f"Généré le {resultats['date'].replace('T', ' à ')} par `python -m src.validation`.",
        "",
        f"Réglages : {g['segments_en_base']} segments en base · embedding `{modele}` · "
        f"segments de {g.get('taille') or '?'} caractères (chevauchement {g.get('chevauchement') or '?'}) · "
        f"Top-K = {g['k']} · seuil = {g['seuil']} · LLM `{g['modele_llm']}`.",
        "",
        "## Résumé",
        "",
        "| Indicateur | Résultat |",
        "|---|---|",
        f"| Questions auxquelles le système a répondu | {r['repondues']} / {r['questions']} |",
        f"| Bon document parmi les sources retrouvées | {r['source_retrouvee']} / {r['questions_avec_source']} |",
        f"| Bon document cité dans la réponse | {r['source_citee']} / {r['questions_avec_source']} |",
        f"| Chiffres attendus présents dans la réponse | {r['chiffres_retrouves']} / {r['questions_avec_chiffres']} |",
        f"| Questions pièges : « je ne sais pas » | {r['pieges_evites']} / {r['pieges']} |",
        f"| Temps moyen de génération | {str(r['generation_moyenne_s']).replace('.', ',')} s |",
        "",
        "Les contrôles de source ne portent que sur les questions dont la colonne « Fichier source » "
        "est remplie dans `docs/questions_validation.md`. La dernière colonne « Correcte » est à "
        "cocher à la main après relecture.",
        "",
        "## Questions de validation",
        "",
        "| # | Question | Réponse attendue | Réponse obtenue | Source retrouvée | Source citée | Chiffres | Score | Correcte |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for l in resultats["questions"]:
        lignes.append(
            f"| {l['numero']} | {_cellule(l['question'])} | {_cellule(l['attendue'])} | {_cellule(l['reponse'])} | "
            f"{_oui_non(l['source_retrouvee'])} | {_oui_non(l['source_citee'])} | {_oui_non(l['chiffres_retrouves'])} | "
            f"{l['meilleur_score']:.2f} | ⬜ |")
    lignes += ["", "## Questions pièges (hors corpus)", "",
               "| Question | Réponse obtenue | LLM appelé | Score | Résultat |", "|---|---|---|---|---|"]
    for p in resultats["pieges"]:
        lignes.append(f"| {_cellule(p['question'])} | {_cellule(p['reponse'])} | {'oui' if p['llm_appele'] else 'non'} | "
                      f"{p['meilleur_score']:.2f} | {'✅ piège évité' if p['evite'] else '❌ le système a répondu'} |")
    lignes += ["", "## Sources utilisées", ""]
    for l in resultats["questions"]:
        cites = [s for s in l["sources"] if s["citee"]] or l["sources"][:1]
        if not cites:
            continue
        details = " ; ".join(f"[{s['numero']}] {Path(s['fichier'] or '').name} — {s['position'] or '?'} ({s['score']:.2f})"
                             for s in cites)
        lignes.append(f"- **{l['numero']}.** {details}")
    return "\n".join(lignes) + "\n"


# --------------------------------------------------------------------- ligne de commande

def main(argv: list[str] | None = None) -> int:
    from .embeddings import MODELE_PAR_DEFAUT, EncodeurLocal
    from .llm import MODELE_LLM_PAR_DEFAUT, ClientOllama, OllamaIndisponible
    from .vectorstore import BaseChroma

    analyseur = argparse.ArgumentParser(description="Validation finale avec les questions de validation (étape 8)")
    analyseur.add_argument("-k", type=int, default=K_PAR_DEFAUT)
    analyseur.add_argument("--seuil", type=float, default=SEUIL_PAR_DEFAUT)
    analyseur.add_argument("--llm", default=MODELE_LLM_PAR_DEFAUT, help="modèle Ollama (mistral, llama3.1…)")
    analyseur.add_argument("--questions", type=Path, default=RACINE / "docs" / "questions_validation.md")
    analyseur.add_argument("--rapport", type=Path, default=RACINE / "docs" / "rapport_validation.md")
    analyseur.add_argument("--json", type=Path, default=RACINE / "data" / "validation.json")
    args = analyseur.parse_args(argv)
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    base = BaseChroma(RACINE / "data" / "chroma")
    if not base.compter():
        print("La base est vide : lancez d'abord l'indexation (POST /index).")
        return 1
    encodeur = EncodeurLocal(base.reglages().get("modele", MODELE_PAR_DEFAUT))
    questions, pieges = lire_jeu(args.questions)

    def progression(rang, total, question):
        print(f"[{rang}/{total}] {question}", flush=True)

    try:
        resultats = valider(questions, pieges, base, encodeur, ClientOllama(args.llm),
                            args.k, args.seuil, progression)
    except OllamaIndisponible as erreur:
        print(f"\n✘ {erreur}\n")
        return 1

    args.rapport.write_text(rapport_markdown(resultats), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(resultats, ensure_ascii=False, indent=2), encoding="utf-8")
    r = resultats["resume"]
    print(f"\nRépondues : {r['repondues']}/{r['questions']} · bonne source citée : "
          f"{r['source_citee']}/{r['questions_avec_source']} · pièges évités : {r['pieges_evites']}/{r['pieges']}")
    print(f"Rapport : {args.rapport}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
