# WebCognitive Engine — Alimentation & Nutrition

Projet individuel du cours **Techniques Informatiques et Web**.
Objectif final : un moteur de recherche sémantique et un assistant (RAG, 100 % local)
capable de répondre à des questions sur un corpus de documents consacré à
**l'alimentation et la nutrition**.

## Avancement

| Étape | Contenu | État |
|---|---|---|
| 1 | Cadrage, corpus et stratégie d'ingestion | 🟡 corpus à télécharger |
| 2 | Pipeline d'ingestion et de parsing | ✅ code et tests |
| 3 | Chunking et embeddings | ⬜ |
| 4 | Base vectorielle et API FastAPI | ⬜ |
| 5 | RAG avec LLM local (Ollama) | ⬜ |
| 6 | Front-end web | ⬜ |
| 7 | Dataviz | ⬜ |
| 8 | Validation finale et soutenance | ⬜ |

## Arborescence

```
webcognitive/
├── data/
│   ├── raw/                 ← documents bruts, NON modifiés
│   │   ├── pdf/
│   │   ├── html/
│   │   ├── docx/
│   │   └── txt/
│   └── processed/           ← texte nettoyé (JSON), généré par le pipeline
├── src/
│   ├── parsers.py           ← lecture PDF / HTML / DOCX / TXT
│   ├── cleaning.py          ← nettoyage et normalisation du texte
│   └── ingest.py            ← pipeline complet + rapport
├── tests/
│   └── test_ingestion.py
├── docs/
│   ├── cahier_des_charges.md
│   ├── sources.md           ← où trouver les documents
│   └── questions_validation.md
├── corpus_metadata.json     ← fiche descriptive de chaque document
├── requirements.txt
└── .gitignore
```

## Installation de l'environnement

```bash
python -m venv venv
# Linux / macOS
source venv/bin/activate
# Windows
venv\Scripts\activate

pip install -r requirements.txt
```

## Règles de nommage des fichiers du corpus

- minuscules, sans accents ni espaces : `pnns_recommandations_2019.pdf`
- forme conseillée : `source_sujet_annee.extension`
- chaque fichier ajouté dans `data/raw/` doit avoir son entrée dans `corpus_metadata.json`

## Étape 2 — Lancer l'ingestion

```bash
python -m src.ingest                                # traite tout data/raw/
python -m src.ingest --fichier data/raw/pdf/x.pdf   # teste un seul fichier
python -m pytest -v                                 # lance les tests
```

Pour chaque document, le pipeline :
1. **lit** le fichier selon son format (pages du PDF, sections `<h1>`–`<h4>` du HTML,
   titres Word du DOCX, titres `#` ou en MAJUSCULES du TXT) ;
2. **nettoie** le texte : Unicode normalisé, ligatures (`ﬁ` → `fi`), espaces insécables,
   césures de fin de ligne, en-têtes / pieds de page et numéros de page des PDF,
   menus / pieds de page / scripts des pages HTML ;
3. **écrit** `data/processed/<id>.json` : texte découpé en **blocs**, chacun avec sa
   position (`page 3`, `section : Le sel`) pour pouvoir citer la source plus tard.

Le fichier `data/processed/rapport_ingestion.json` fait le bilan et signale :
PDF probablement scannés, fichiers sans fiche dans `corpus_metadata.json`,
fiches dont le fichier est introuvable, `nombre_documents` incohérent, encodage non UTF-8.

Exemple de sortie :

```json
{
  "id": "doc_001",
  "fichier": "data/raw/html/sante_fr_sel.html",
  "format": "html",
  "titre": "Limiter les produits salés et le sel",
  "metadonnees": { "...": "entrée de corpus_metadata.json" },
  "statistiques": { "nombre_blocs": 4, "nombre_pages": null, "nombre_caracteres": 3120, "nombre_mots": 512 },
  "avertissements": [],
  "blocs": [
    { "numero": 1, "position": "section : Le sel", "page": null, "section": "Le sel", "texte": "..." }
  ]
}
```
