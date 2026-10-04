# WebCognitive Engine — Alimentation & Nutrition

Projet individuel du cours **Techniques Informatiques et Web**.
Objectif final : un moteur de recherche sémantique et un assistant (RAG, 100 % local)
capable de répondre à des questions sur un corpus de documents consacré à
**l'alimentation et la nutrition**.

## Avancement

| Étape | Contenu | État |
|---|---|---|
| 1 | Cadrage, corpus et stratégie d'ingestion | 🟡 en cours |
| 2 | Pipeline d'ingestion et de parsing | ⬜ |
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
│   └── raw/                 ← documents bruts, NON modifiés
│       ├── pdf/
│       ├── html/
│       ├── docx/
│       └── txt/
├── src/                     ← code Python (à partir de l'étape 2)
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
