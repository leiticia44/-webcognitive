# Manuel d'utilisation — WebCognitive Engine

Ce manuel explique comment utiliser l'application une fois installée
(voir l'installation dans le [README](../README.md)). Les détails techniques se trouvent
dans la [spécification technique](specification_technique.md).

## 1. Démarrer l'application

Depuis le dossier du projet, environnement virtuel activé :

```bash
uvicorn src.api:app
```

Sous Windows, sans activer l'environnement : `venv\Scripts\python.exe -m uvicorn src.api:app`.

Attendre la ligne `Uvicorn running on http://127.0.0.1:8000`, puis ouvrir dans le navigateur :

| Adresse | Page |
|---|---|
| http://127.0.0.1:8000/ | l'assistant : poser une question |
| http://127.0.0.1:8000/app/dataviz.html | le tableau de bord du corpus |
| http://127.0.0.1:8000/docs | l'API, avec sa documentation interactive (Swagger) |

La fenêtre du terminal doit rester ouverte : la fermer arrête l'application (Ctrl + C aussi).

## 2. Indexer le corpus (première utilisation)

La base est vide tant que le corpus n'a pas été indexé. Deux possibilités :
- dans l'assistant, ouvrir **Réglages de la recherche** puis cliquer sur **Réindexer le corpus** ;
- dans l'API (`/docs`), ouvrir **POST /index**, cliquer sur **Try it out** puis **Execute**.

L'indexation lit tous les documents de `data/raw/`, les découpe, calcule les vecteurs et les
enregistre dans `data/chroma/`. Sur le corpus complet (27 documents), elle dure environ
15 minutes sur un ordinateur portable sans carte graphique ; la première fois, le modèle
d'embedding (environ 470 Mo) est aussi téléchargé. La base est conservée sur le disque :
il n'est nécessaire de réindexer qu'après avoir ajouté, modifié ou retiré des documents.

## 3. Poser une question

1. Écrire la question dans la zone en bas de l'écran, par exemple
   « Combien de fois par semaine faut-il manger du poisson ? ».
2. Cliquer sur **Poser la question** ou appuyer sur Entrée (Maj + Entrée pour aller à la ligne).

La réponse s'affiche avec ses sources :

| Élément | Signification |
|---|---|
| **[1]**, **[2]** dans la réponse | numéros des sources ; un clic ouvre le passage correspondant |
| Carte de source | nom du fichier, page ou section, titre du document |
| Jauge colorée | pertinence du passage (similarité avec la question), du rouge au vert |
| Voir le passage | le texte exact du document utilisé pour répondre |
| Autres passages consultés | les passages trouvés mais non utilisés dans la réponse |

### Les deux modes de réponse

- **Mode génératif** (Ollama et Mistral installés) : le modèle de langage rédige la réponse à
  partir des passages trouvés, en citant ses sources.
- **Mode extractif** (Ollama absent ou arrêté) : l'application recopie telles quelles les phrases
  du meilleur passage, entre guillemets. Une mention l'indique sous la réponse. Ce mode ne peut
  rien inventer, mais la réponse est parfois moins bien tournée.

Si aucun passage n'est assez proche de la question, l'application répond qu'elle ne sait pas.

### Réglages de la recherche

Sous la zone de question, **Réglages de la recherche** permet de choisir :
- le nombre de passages consultés (5 par défaut) ;
- le seuil de pertinence en dessous duquel l'application répond « je ne sais pas » ;
- le format des documents (tous, PDF, pages web, Word, texte) ;
- le modèle de langage d'Ollama (`mistral` par défaut).

## 4. Explorer le tableau de bord

Bouton **Tableau de bord** en haut de l'assistant, ou http://127.0.0.1:8000/app/dataviz.html.

- **Chiffres clés** : documents, segments, mots, formats.
- **Filtre par format** : s'applique aux graphiques des documents, à la carte et au tableau.
- **Survol** : passer la souris sur une barre, un point ou une case affiche le détail.
- **Carte sémantique** : chaque point est un passage ; deux points proches parlent du même sujet.
- **Proximité entre documents** : plus la case est foncée, plus deux documents se ressemblent.
- **Tableau des documents** : les mêmes informations en texte, avec les mots-clés de chaque document.

## 5. Ajouter des documents au corpus

1. Copier le fichier dans le bon dossier : `data/raw/pdf`, `data/raw/html`, `data/raw/docx` ou `data/raw/txt`.
2. Lancer l'ingestion : `python -m src.ingest`. Le rapport signale les problèmes
   (PDF scanné sans texte, encodage, fichier sans fiche).
3. Créer les fiches manquantes : `python -m src.metadonnees --ecrire`, puis compléter dans
   `corpus_metadata.json` les champs marqués « à compléter » (date, URL).
4. Réindexer (section 2).

## 6. Vérifier la qualité des réponses

```bash
python -m src.validation
```

Le script pose les 15 questions de `docs/questions_validation.md` et les questions pièges, puis écrit
`docs/rapport_validation.md` : réponse attendue et réponse obtenue côte à côte, source retrouvée ou non,
chiffres présents ou non. Il fonctionne aussi sans Ollama (mode extractif).

## 7. En cas de problème

| Message ou symptôme | Cause | Solution |
|---|---|---|
| « python n'est pas reconnu » (Windows) | Python n'est pas dans le PATH | utiliser `venv\Scripts\python.exe` à la place de `python` |
| Les commandes n'affichent rien dans PowerShell | scripts bloqués par la politique d'exécution | utiliser l'Invite de commandes (`cmd`) |
| « Le chemin d'accès spécifié est introuvable » | la commande n'est pas lancée depuis le dossier du projet | `cd` vers le dossier du projet d'abord |
| `error while attempting to bind on address … 8000` | l'application tourne déjà dans une autre fenêtre | arrêter l'autre fenêtre (Ctrl + C) |
| « La base est vide » | le corpus n'a pas été indexé | indexer (section 2) |
| « Modèle de langage indisponible (Ollama) » | Ollama n'est pas lancé ou le modèle n'est pas téléchargé | normal en mode extractif ; sinon lancer Ollama et `ollama pull mistral` |
| `No space left on device`, `database or disk is full` | disque plein | libérer de la place (`pip cache purge`, fichiers temporaires), au moins 2 Go |
| `Authentication failed` lors d'un `git push` | GitHub refuse les mots de passe | se connecter à GitHub depuis VS Code, ou utiliser un jeton d'accès |
| L'indexation semble bloquée | le calcul des vecteurs est long sur processeur | attendre : la barre `Batches` du terminal indique la progression |
