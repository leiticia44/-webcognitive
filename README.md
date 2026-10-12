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
| 3 | Chunking et embeddings | ✅ code et tests |
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
│   ├── processed/           ← texte nettoyé (JSON), généré à l'étape 2
│   └── vectors/             ← segments et vecteurs, générés à l'étape 3
├── src/
│   ├── parsers.py           ← lecture PDF / HTML / DOCX / TXT
│   ├── cleaning.py          ← nettoyage et normalisation du texte
│   ├── ingest.py            ← pipeline d'ingestion + rapport (étape 2)
│   ├── chunking.py          ← découpage en segments avec chevauchement
│   ├── embeddings.py        ← modèle d'embedding local, similarité cosinus
│   ├── vectorize.py         ← découpage + vectorisation du corpus (étape 3)
│   └── evaluate.py          ← test et optimisation avec les questions de validation
├── tests/
│   ├── test_ingestion.py
│   └── test_vectorisation.py
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

# Facultatif mais conseillé : PyTorch en version CPU (beaucoup plus léger)
pip install torch --index-url https://download.pytorch.org/whl/cpu

pip install -r requirements.txt
```

Le modèle d'embedding est téléchargé automatiquement au premier lancement
de l'étape 3 (environ 470 Mo pour le modèle multilingue), puis tout s'exécute en local.

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

## Étape 3 — Découpage et vectorisation

```bash
python -m src.vectorize                     # segments de 500 caractères, chevauchement 100
python -m src.vectorize --sans-vecteurs     # découpage seul, pour vérifier les tailles
python -m src.evaluate --details            # tester plusieurs tailles avec les questions de validation
python -m src.evaluate --modeles multilingue,minilm   # comparer les deux modèles
```

**1. Découpage (chunking).** Chaque bloc de l'étape 2 est découpé en phrases,
puis les phrases sont regroupées jusqu'à environ 500 caractères. Le segment suivant
reprend les dernières phrases du précédent (chevauchement d'environ 100 caractères) :
une idée n'est jamais coupée entre deux segments. Règles :
- on ne coupe jamais au milieu d'une phrase (les abréviations « p. 12 », « env. 5 »,
  « M. Dupont » ne sont pas prises pour des fins de phrase) ; seule une phrase plus longue
  que la taille maximale est coupée, sur les espaces ;
- un segment ne déborde jamais de son bloc : il garde sa page ou sa section d'origine ;
- un dernier segment trop petit (moins d'un quart de la taille) est fusionné avec le précédent ;
- le texte vectorisé commence par le titre du document et la section
  (« Le sel — Où se cache le sel ? : … ») pour donner du contexte aux petits segments.

**2. Vectorisation.** Chaque segment devient un vecteur de 384 nombres grâce à
sentence-transformers, exécuté en local sur le processeur. Les vecteurs sont normalisés :
la similarité cosinus entre une question et un segment est alors un simple produit scalaire.

| Modèle | Option | Pourquoi |
|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2 | `multilingue` (par défaut) | entraîné sur plus de 50 langues dont le français ; 384 dimensions |
| all-MiniLM-L6-v2 | `minilm` | modèle cité dans la fiche ; plus rapide, mais entraîné surtout sur de l'anglais |

Le corpus étant en français, le modèle multilingue est utilisé par défaut ;
`python -m src.evaluate --modeles multilingue,minilm` permet de vérifier ce choix sur nos questions.

**3. Sorties** (`data/vectors/`) :
- `segments.jsonl` : un segment par ligne, avec son document, sa page ou section
  et ses positions de début et de fin dans le bloc ;
- `embeddings.npy` : la matrice des vecteurs (une ligne par segment, dans le même ordre) ;
- `index.json` : modèle, taille, chevauchement, durée et statistiques.

**4. Test et optimisation.** `python -m src.evaluate` découpe et vectorise le corpus
pour plusieurs tailles (250, 500, 800, 1200 caractères), pose chaque question de
`docs/questions_validation.md` et mesure si le bon document arrive en tête :

| Mesure | Signification |
|---|---|
| Top-1 / Top-3 / Top-5 | part des questions dont le bon document est dans les 1, 3 ou 5 premiers segments |
| MRR | moyenne de 1 / rang du premier bon segment (1 = toujours premier) |
| Pos. | bonne page ou section dans le top-5 |
| Score / Piège | similarité du meilleur segment pour les vraies questions, et la plus haute obtenue par une question hors corpus |

Des segments trop petits manquent de contexte ; trop grands, ils mélangent plusieurs
sujets et le sens se dilue. La meilleure configuration est marquée ◀ et les résultats
sont enregistrés dans `data/vectors/evaluation.json`. L'écart entre « Score » et « Piège »
servira à fixer, à l'étape 5, le seuil sous lequel l'assistant répond que l'information
n'est pas dans le corpus.

⚠️ Seules les questions dont la colonne « Fichier source » est remplie sont évaluées.
