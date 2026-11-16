# Questions de validation

Ces questions servent de **jeu de test** pour tout le projet : à chaque étape,
le moteur doit retrouver la bonne réponse **et** la bonne source.

**Méthode (audit manuel, avant tout code) :**
1. Ouvrir le document à la main.
2. Repérer un passage précis (chiffre, tableau, définition, date).
3. Recopier la réponse **exactement** telle qu'elle est écrite.
4. Noter le fichier, la page (PDF) ou la section (HTML/DOCX/TXT).
5. Cocher « Vérifiée » seulement après cette relecture.

> ⚠️ Les réponses attendues ci-dessous ont été **pré-vérifiées sur les sites officiels**
> (colonne « Source de référence »). Il reste à les **retrouver dans les fichiers
> réellement téléchargés**, à recopier la formulation exacte et à remplir les colonnes
> « Fichier source » et « Page / section ».

| # | Question | Réponse attendue | Source de référence | Format visé | Fichier source | Page / section | Vérifiée |
|---|---|---|---|---|---|---|---|
| 1 | Combien de portions de fruits et légumes faut-il manger par jour ? | Au moins 5 (par exemple 3 portions de légumes et 2 fruits) | Recommandations Santé publique France 2019 | PDF | 244900_spf00001365.pdf | page 2 | ✅ |
| 2 | Combien de lettres compte le Nutri-Score ? | 5 lettres, de A (vert foncé) à E (orange foncé) | santepubliquefrance.fr, page Nutri-Score | HTML | note_nutriscore.docx | section : Qu'est-ce que le Nutri-Score ? | ✅ |
| 3 | Depuis quand le Nutri-Score est-il recommandé en France ? | Depuis le 31 octobre 2017 (arrêté interministériel) | santepubliquefrance.fr, page Nutri-Score | HTML | note_nutriscore.docx | section : Depuis quand existe-t-il en France ? | ✅ |
| 4 | Quelle quantité maximale de sel par jour est recommandée pour un adulte ? | 5 g de sel par jour (soit 2,4 g de sodium) | sante.fr / Manger Bouger, fiche sel | HTML | 244900_spf00001365.pdf | page 1 | ✅ |
| 5 | Combien de minutes d'activité physique par jour sont recommandées pour un adulte ? | Au moins 30 minutes d'activité physique dynamique par jour | Recommandations Santé publique France 2019 | PDF | Augmenter l'activité physique _ Manger Bouger.html | section : La recommandation | ✅ |
| 6 | Combien de fois par semaine faut-il manger du poisson ? | 2 fois par semaine, dont 1 poisson gras | Recommandations Santé publique France 2019 | PDF | Aller vers les poissons gras et maigres en alternance _ Manger Bouger.html | section : La recommandation | ✅ |
| 7 | À quelle fréquence faut-il manger des légumineuses (lentilles, pois chiches…) ? | Au moins 2 fois par semaine | Recommandations Santé publique France 2019 | PDF | 244900_spf00001365.pdf | page 2 | ❌ |
| 8 | Quelle est la limite recommandée pour la viande hors volaille par semaine ? | 500 g par semaine (environ 3 ou 4 steaks) | sante.fr / Manger Bouger, fiche viande | HTML | 42466_spf00000619.pdf | page 36 | ✅ |
| 9 | Quelle part des adultes français est en surpoids ou obèse ? | Étude ESTEBAN 2015 : 54 % des hommes et 44 % des femmes en surpoids (obésité incluse) ; 17 % des adultes obèses | Santé publique France, ESTEBAN 2014-2016, chapitre corpulence | PDF |  |  | ❌ |
| 10 | Quelle est la seule boisson indispensable selon les recommandations ? | L'eau | Manger Bouger / recommandations PNNS | HTML |  |  | ❌ |
| 11 | Quelle quantité maximale de charcuterie est recommandée par semaine ? | 150 g par semaine | Recommandations Santé publique France 2019 | PDF |  |  | ❌ |
| 12 | Que signifie le sigle PNNS ? | Programme national nutrition santé | Wikipédia, « Programme national nutrition santé » | HTML |  |  | ❌ |
| 13 | À partir de quel IMC parle-t-on d'obésité chez l'adulte ? | IMC supérieur ou égal à 30 kg/m² | Wikipédia « Obésité » ou ameli.fr | HTML |  |  | ❌ |
| 14 | Quels sont les grands groupes d'aliments et leur rôle principal ? | Fruits et légumes (fibres, vitamines, minéraux), féculents (énergie), légumes secs (protéines végétales, fibres), produits laitiers (calcium), viandes-poissons-œufs (protéines, fer), matières grasses (acides gras indispensables) | Ma note « Les groupes d'aliments et leurs rôles » | DOCX | note_groupes_aliments.docx | section : Tableau récapitulatif | ⚠️ |
| 15 | Qu'est-ce qu'un produit ultra-transformé ? | À recopier depuis l'article téléchargé | Article sur les produits ultra-transformés | TXT |  |  | ❌ |

Répartition visée : PDF (1, 5, 6, 7, 9, 11), HTML (2, 3, 4, 8, 10, 12, 13), DOCX (14), TXT (15).

### Résultats du premier passage (16/11/2026)

Lancé avec `python -m src.validation` sur le corpus complet (27 documents, 9 690 segments),
en **mode extractif** (sans Ollama), Top-K = 5, seuil = 0,30.

- ✅ **7 / 15** : bonne réponse et bonne source (1, 2, 3, 4, 5, 6, 8). Pour la question 4, la
  réponse cite les 5 g de sel recommandés par l'OMS, sans l'équivalent en sodium.
- ⚠️ **14** : la bonne note est retrouvée parmi les 5 passages, mais le passage classé premier
  est un tableau de l'Anses (`NUT2012SA0103Ra-1.pdf`, page 168).
- ❌ **7** : la réponse (« des légumes secs au moins 2 fois par semaine ») est bien dans
  `244900_spf00001365.pdf` page 2, mais le mot « légumineuses » de la question l'a fait manquer.
- ❌ **9, 10, 11, 12, 13, 15** : passages voisins du sujet mais sans la réponse exacte
  (ESTEBAN, l'eau, la charcuterie, le sens du sigle PNNS, le seuil d'IMC, la définition des
  produits ultra-transformés). À vérifier à la main dans les documents, puis reformuler la
  question ou remplacer la source.

Constat sur le seuil : avec ce modèle, les bonnes réponses obtiennent un score de 0,63 à 0,86,
mais les questions hors sujet obtiennent déjà 0,61-0,62. Le seuil de 0,30 ne filtre donc rien ;
en mode génératif, c'est le prompt strict du LLM qui doit répondre « je ne sais pas ».
Si un document ne contient finalement pas la réponse, remplacer la question plutôt que de la garder.

## Question « piège » (hors corpus)

Pour tester plus tard que l'IA n'invente pas de réponse :

| Question | Comportement attendu |
|---|---|
| Qui a gagné la Coupe du monde de football 2018 ? | L'application indique que l'information n'est pas dans le corpus |
| Quel est le meilleur régime pour perdre 10 kg en un mois ? | L'application indique que l'information n'est pas dans le corpus (hors périmètre : régimes « miracles ») |

La première question piège était « Quelle est la recette de la blanquette de veau ? ». Elle a été
remplacée le 16/11/2026 : le corpus contient en réalité une recette de blanquette
(`spf00001656.pdf`, page 58). Ce n'était donc plus une question hors corpus.

