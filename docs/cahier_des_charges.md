# Cahier des charges — WebCognitive Engine

## 1. Thématique

**Alimentation et nutrition** : recommandations alimentaires officielles en France,
groupes d'aliments, Nutri-Score, équilibre alimentaire selon les publics
(enfants, adultes, seniors, femmes enceintes), activité physique associée,
et enjeux de santé publique liés à l'alimentation (surpoids, obésité).

### Hors périmètre
- Recettes de cuisine et gastronomie
- Régimes « miracles » ou contenus non scientifiques
- Conseils médicaux individuels

## 2. Objectif de l'application

Permettre à un utilisateur de poser une question en langage naturel
(ex. : « Combien de portions de fruits et légumes faut-il manger par jour ? »)
et d'obtenir une réponse **fondée uniquement sur le corpus**, accompagnée
des **sources citées** (document et passage).

## 3. Public visé

Grand public, étudiants, personnes souhaitant comprendre les recommandations
nutritionnelles officielles.

## 4. Fonctionnalités prévues

| # | Fonctionnalité | Étape |
|---|---|---|
| F1 | Lecture automatique des formats PDF, HTML, DOCX, TXT | 2 |
| F2 | Nettoyage et normalisation du texte | 2 |
| F3 | Découpage en passages (chunking) et vectorisation (embeddings) | 3 |
| F4 | Stockage dans une base vectorielle (ChromaDB ou FAISS) | 4 |
| F5 | API REST (FastAPI) : indexation et recherche | 4 |
| F6 | Réponse générée par un LLM local (Ollama) avec citation des sources | 5 |
| F7 | Interface web de recherche / conversation | 6 |
| F8 | Tableau de bord de visualisation du corpus | 7 |

## 5. Corpus

- **35 à 50 documents**, tous sur le thème de l'alimentation et de la nutrition
- **4 formats** : PDF, HTML, DOCX, TXT
- Sources **publiques, gratuites et fiables** (voir `sources.md`)
- Chaque document est décrit dans `corpus_metadata.json`

| Format | Objectif |
|---|---|
| PDF | ~12 |
| HTML | ~12 |
| DOCX | ~6 |
| TXT | ~5 |

## 6. Contraintes

- **100 % local** et **logiciels libres** : aucun service cloud payant
- Langage : Python (environnement virtuel `venv`)
- Versioning : Git, commits réguliers et explicites
- Traçabilité : toute réponse doit pouvoir être reliée à un document source

## 7. Critères de réussite

- Le système retrouve la bonne réponse et la bonne source pour les questions
  listées dans `questions_validation.md`
- Aucune réponse inventée (« hallucination ») : si l'information n'est pas
  dans le corpus, l'application le dit
