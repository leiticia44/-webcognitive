"""Pipeline d'ingestion : data/raw/  ->  data/processed/

Usage (depuis la racine du projet, venv activé) :

    python -m src.ingest                 # traite tout data/raw/
    python -m src.ingest --fichier data/raw/pdf/mon_doc.pdf   # un seul fichier

Pour chaque document, produit data/processed/<id>.json contenant le texte
nettoyé découpé en blocs (page ou section) et les métadonnées du corpus.
Produit aussi data/processed/rapport_ingestion.json : bilan, erreurs et
avertissements (PDF scannés, métadonnées manquantes…).

Les fichiers de data/raw/ ne sont JAMAIS modifiés.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from .parsers import EXTENSIONS, FormatNonSupporte, parser_fichier

RACINE = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ métadonnées

def charger_metadonnees(chemin: Path) -> tuple[dict, list[dict]]:
    """Renvoie (fichier complet, liste des documents)."""
    if not chemin.exists():
        return {}, []
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    return donnees, donnees.get("documents", [])


def normaliser_chemin(chemin: str) -> str:
    """Chemin relatif à la racine, avec des / (pour comparer Windows et Linux)."""
    return chemin.replace("\\", "/").lstrip("./")


def verifier_metadonnees(meta: dict, documents: list[dict], fichiers: list[Path], racine: Path) -> list[str]:
    """Contrôles de cohérence entre corpus_metadata.json et data/raw/."""
    problemes = []
    ids = Counter(d.get("id") for d in documents)
    for doc_id, n in ids.items():
        if n > 1:
            problemes.append(f"id en double dans corpus_metadata.json : {doc_id}")

    declares = {normaliser_chemin(d.get("fichier", "")): d for d in documents}
    presents = {normaliser_chemin(f.relative_to(racine).as_posix()) for f in fichiers}

    for chemin in sorted(declares.keys() - presents):
        problemes.append(f"déclaré dans corpus_metadata.json mais introuvable : {chemin}")
    for chemin in sorted(presents - declares.keys()):
        problemes.append(f"présent dans data/raw/ mais sans entrée dans corpus_metadata.json : {chemin}")

    for chemin, d in declares.items():
        ext = Path(chemin).suffix.lower()
        if d.get("format") and EXTENSIONS.get(ext) and d["format"] != EXTENSIONS[ext]:
            problemes.append(f"format « {d['format']} » incohérent avec l'extension : {chemin}")

    annonce = meta.get("nombre_documents")
    if annonce is not None and annonce != len(documents):
        problemes.append(
            f"nombre_documents vaut {annonce} mais la liste contient {len(documents)} documents"
        )
    return problemes


def identifiant(chemin: Path) -> str:
    """Identifiant de secours quand le fichier n'a pas d'entrée de métadonnées."""
    return "sans_meta_" + re.sub(r"[^a-z0-9_]+", "_", chemin.stem.lower())


# ---------------------------------------------------------------------- pipeline

def lister_fichiers(dossier_raw: Path) -> list[Path]:
    return sorted(
        f for f in dossier_raw.rglob("*")
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in EXTENSIONS
    )


def traiter(chemin: Path, entree_meta: dict | None, racine: Path) -> dict:
    """Parse un fichier et construit l'enregistrement JSON."""
    doc = parser_fichier(chemin)
    entree_meta = entree_meta or {}
    textes = [b.texte for b in doc.blocs]
    texte_complet = "\n\n".join(textes)
    return {
        "id": entree_meta.get("id") or identifiant(chemin),
        "fichier": chemin.relative_to(racine).as_posix(),
        "format": doc.format,
        # Le titre saisi à la main dans les métadonnées est prioritaire sur celui détecté
        "titre": entree_meta.get("titre") or doc.titre or chemin.stem,
        "metadonnees": entree_meta,
        "statistiques": {
            "nombre_blocs": len(doc.blocs),
            "nombre_pages": doc.nombre_pages,
            "nombre_caracteres": len(texte_complet),
            "nombre_mots": len(texte_complet.split()),
        },
        "avertissements": doc.avertissements,
        "blocs": [
            {
                "numero": i,
                "position": b.position,
                "page": b.page,
                "section": b.section,
                "texte": b.texte,
            }
            for i, b in enumerate(doc.blocs, start=1)
        ],
    }


def executer(dossier_raw: Path, dossier_sortie: Path, fichier_meta: Path,
             racine: Path, seulement: Path | None = None) -> dict:
    meta, documents = charger_metadonnees(fichier_meta)
    par_chemin = {normaliser_chemin(d.get("fichier", "")): d for d in documents}

    tous = lister_fichiers(dossier_raw)
    a_traiter = [seulement.resolve()] if seulement else tous
    dossier_sortie.mkdir(parents=True, exist_ok=True)

    rapport = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "documents_traites": 0,
        "par_format": {},
        "total_mots": 0,
        "erreurs": [],
        "avertissements": [],
        "controles_metadonnees": verifier_metadonnees(meta, documents, tous, racine) if not seulement else [],
        "documents": [],
    }
    par_format: Counter = Counter()

    for chemin in a_traiter:
        relatif = chemin.relative_to(racine).as_posix()
        try:
            enregistrement = traiter(chemin, par_chemin.get(normaliser_chemin(relatif)), racine)
        except FormatNonSupporte as erreur:
            rapport["erreurs"].append({"fichier": relatif, "erreur": str(erreur)})
            continue
        except Exception as erreur:  # fichier corrompu, protégé par mot de passe…
            rapport["erreurs"].append({"fichier": relatif, "erreur": f"{type(erreur).__name__} : {erreur}"})
            continue

        sortie = dossier_sortie / f"{enregistrement['id']}.json"
        sortie.write_text(json.dumps(enregistrement, ensure_ascii=False, indent=2), encoding="utf-8")

        stats = enregistrement["statistiques"]
        par_format[enregistrement["format"]] += 1
        rapport["documents_traites"] += 1
        rapport["total_mots"] += stats["nombre_mots"]
        for avertissement in enregistrement["avertissements"]:
            rapport["avertissements"].append({"fichier": relatif, "avertissement": avertissement})
        rapport["documents"].append({
            "id": enregistrement["id"],
            "fichier": relatif,
            "format": enregistrement["format"],
            "titre": enregistrement["titre"],
            "blocs": stats["nombre_blocs"],
            "mots": stats["nombre_mots"],
            "sortie": sortie.relative_to(racine).as_posix(),
        })

    rapport["par_format"] = dict(sorted(par_format.items()))
    if not seulement:
        (dossier_sortie / "rapport_ingestion.json").write_text(
            json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return rapport


def afficher(rapport: dict) -> None:
    print(f"\nDocuments traités : {rapport['documents_traites']}  "
          f"({', '.join(f'{k}: {v}' for k, v in rapport['par_format'].items()) or 'aucun'})")
    print(f"Total : {rapport['total_mots']} mots\n")
    for d in rapport["documents"]:
        print(f"  ✔ {d['fichier']:<60} {d['blocs']:>4} blocs {d['mots']:>7} mots")
    for e in rapport["erreurs"]:
        print(f"  ✘ {e['fichier']} — {e['erreur']}")
    if rapport["avertissements"]:
        print("\nAvertissements :")
        for a in rapport["avertissements"]:
            print(f"  ⚠ {a['fichier']} — {a['avertissement']}")
    if rapport["controles_metadonnees"]:
        print("\nContrôles de corpus_metadata.json :")
        for p in rapport["controles_metadonnees"]:
            print(f"  ⚠ {p}")
    print()


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(description="Ingestion du corpus WebCognitive")
    analyseur.add_argument("--raw", type=Path, default=RACINE / "data" / "raw")
    analyseur.add_argument("--sortie", type=Path, default=RACINE / "data" / "processed")
    analyseur.add_argument("--metadonnees", type=Path, default=RACINE / "corpus_metadata.json")
    analyseur.add_argument("--fichier", type=Path, help="ne traiter qu'un seul fichier")
    args = analyseur.parse_args(argv)

    rapport = executer(args.raw.resolve(), args.sortie.resolve(), args.metadonnees.resolve(),
                       RACINE, args.fichier)
    afficher(rapport)
    return 1 if rapport["erreurs"] else 0


if __name__ == "__main__":
    sys.exit(main())
