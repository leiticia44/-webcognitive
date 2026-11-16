# Rapport de validation — WebCognitive Engine

Généré le 2026-11-16 à 12:42:14 par `python -m src.validation`.

Réglages : 9690 segments en base · embedding `paraphrase-multilingual-MiniLM-L12-v2` · segments de 500 caractères (chevauchement 100) · Top-K = 5 · seuil = 0.3 · LLM `mistral`.

## Résumé

| Indicateur | Résultat |
|---|---|
| Questions auxquelles le système a répondu | 15 / 15 |
| Bon document parmi les sources retrouvées | 1 / 1 |
| Bon document cité dans la réponse | 0 / 1 |
| Chiffres attendus présents dans la réponse | 7 / 11 |
| Questions pièges : « je ne sais pas » | 0 / 2 |
| Temps moyen de génération | 2,23 s |

Mode **extractif** : le modèle de langage (Ollama) n'était pas disponible, les réponses sont recopiées du meilleur passage.

Les contrôles de source ne portent que sur les questions dont la colonne « Fichier source » est remplie dans `docs/questions_validation.md`. La dernière colonne « Correcte » est à cocher à la main après relecture.

## Questions de validation

| # | Question | Réponse attendue | Réponse obtenue | Source retrouvée | Source citée | Chiffres | Score | Correcte |
|---|---|---|---|---|---|---|---|---|
| 1 | Combien de portions de fruits et légumes faut-il manger par jour ? | Au moins 5 (par exemple 3 portions de légumes et 2 fruits) | « Au moins 5 fruits et légumes par jour (par exemple 3 portions de légumes et 2 fruits) qui apportent des antioxydants, des vitamines et des minéraux. Des légumes secs au moins 2 fois par semaine : lentilles, haricots secs, pois chiches, etc. » [1] | — | — | ✅ | 0.81 | ⬜ |
| 2 | Combien de lettres compte le Nutri-Score ? | 5 lettres, de A (vert foncé) à E (orange foncé) | « Le Nutri-Score est un logo affiché sur l'emballage des produits alimentaires. Il indique la qualité nutritionnelle d'un produit à l'aide d'une échelle de 5 lettres, de A à E, associées à 5 couleurs. » [1] | — | — | ✅ | 0.63 | ⬜ |
| 3 | Depuis quand le Nutri-Score est-il recommandé en France ? | Depuis le 31 octobre 2017 (arrêté interministériel) | « Depuis le 31 octobre 2017, un arrêté interministériel recommande l'utilisation du logo Nutri-Score en France. Son affichage repose sur le volontariat des entreprises : il n'est pas obligatoire. » [1] | — | — | ✅ | 0.80 | ⬜ |
| 4 | Quelle quantité maximale de sel par jour est recommandée pour un adulte ? | 5 g de sel par jour (soit 2,4 g de sodium) | « Consommation trop importante de sel dépassent la limite recommandée par l’Organisation mondiale de la santé de 5 g de sel par jour2, 3. Les apports moyens en acides gras oméga 3 (ALA, DHA, et EPA) des adultes sont environ deux fois trop faibles4. » [1] | — | — | ❌ | 0.74 | ⬜ |
| 5 | Combien de minutes d'activité physique par jour sont recommandées pour un adulte ? | Au moins 30 minutes d'activité physique dynamique par jour | « Pour la fréquence, une formulation par jour et l’autre par semaine ont été proposées (30 min/jour ; 2h30/semaine) ; les types d’activités physiques ont » [1] | — | — | ✅ | 0.86 | ⬜ |
| 6 | Combien de fois par semaine faut-il manger du poisson ? | 2 fois par semaine, dont 1 poisson gras | « 2 fois par semaine, dont un poisson gras (sardines, maquereau, hareng, saumon). Une portion de poisson équivaut à 100g, un petit pavé de saumon ou une boite de sardine. » [1] | — | — | ✅ | 0.78 | ⬜ |
| 7 | À quelle fréquence faut-il manger des légumineuses (lentilles, pois chiches…) ? | Au moins 2 fois par semaine | « Cuisson : 1 heure environ. 500 g de veau à blanquette, 2 c à soupe d’huile, 4 carottes, 1 bouquet garni, 2 c à café de farine, 1 jaune d’œuf, 4 c à café de crème fraîche épaisse, sel, poivre Faire revenir les morceaux de veau avec l’huile dans une cocotte. » [1] | — | — | ✅ | 0.63 | ⬜ |
| 8 | Quelle est la limite recommandée pour la viande hors volaille par semaine ? | 500 g par semaine (environ 3 ou 4 steaks) | « Privilégier la volaille, et limiter les autres viandes (porc, bœuf, veau, mou ton, agneau, abats) à 500 g par semaine. • 500 g de viande hors volaille par semaine, cela correspond à environ 3 ou 4 steaks. » [1] | — | — | ✅ | 0.80 | ⬜ |
| 9 | Quelle part des adultes français est en surpoids ou obèse ? | Étude ESTEBAN 2015 : 54 % des hommes et 44 % des femmes en surpoids (obésité incluse) ; 17 % des adultes obèses | « Chez l’enfant de 2 à 17 ans, la maigreur, le surpoids et l’obésité ont été estimés en fonction de la définition internationale établie par le Childhood Obesity Working Group de l’International Obesity Task Force (IOTF) (Cole et Lobstein 2012). Les valeurs seuils de l’IMC définissant la maigreur, le surpoids et l’obésité sont spécifiques à l’âge et au sexe des enfants. » [1] | — | — | ❌ | 0.78 | ⬜ |
| 10 | Quelle est la seule boisson indispensable selon les recommandations ? | L'eau | « Pour réduire les risques, il est recommandé de limiter sa consommation à deux verres par jour maximum et de ne pas consommer d’alcool tous l es jours : maximum 2 verres par jour et pas tous les jours Les risques liés à la consommation d’alcool pour la santé au cours de la vie augmentent avec la quantité consommée. » [1] | — | — | — | 0.73 | ⬜ |
| 11 | Quelle quantité maximale de charcuterie est recommandée par semaine ? | 150 g par semaine | « La nécessité de faire un calcul mental pour comprendre la recommandation a été également plus élevée pour la formulation « 2h30 par semaine » en comparaison à la formulation « 30 minutes par jour ». Ces résultats suggèrent que la temporalité « 30 minutes par jour » est plus pertinente que « 2h30 par semaine ». » [1] | — | — | ❌ | 0.61 | ⬜ |
| 12 | Que signifie le sigle PNNS ? | Programme national nutrition santé | « Le logo du PNNS a pour objectif, au travers d’une m arque (déposée à l’INPI), de donner de la cohérence aux messages en nutrition portés par dive rs supports, de valoriser les documents produits par des acteurs variés (associations, coll ectivités territoriales, organismes publics ou privés, entreprises publiques ou privées), en leur offrant la possibilité de reconnaître leur conformité au PNNS, et limiter ainsi la diffusion de messages contradictoires. » [1] | — | — | — | 0.65 | ⬜ |
| 13 | À partir de quel IMC parle-t-on d'obésité chez l'adulte ? | IMC supérieur ou égal à 30 kg/m² | « - La prévalence du surpoids et de l’obésité chez les adultes est restée stable (de l’ordre de 49%). - Chez les enfants , la prévalence du surpoids (obésité incluse) est re stée stable (18% en 2006 versus 17% en 2015 ; obésité seule passant de 3% à 4%). » [1] | — | — | ❌ | 0.74 | ⬜ |
| 14 | Quels sont les grands groupes d'aliments et leur rôle principal ? | Fruits et légumes (fibres, vitamines, minéraux), féculents (énergie), légumes secs (protéines végétales, fibres), produits laitiers (calcium), viandes-poissons-œufs (protéines, fer), matières grasses (acides gras indispensables) | « Synthèse des groupes et des sous -groupes constitués pour la catégorisation des aliments Groupes des repères de consommation » [1] | ✅ | ❌ | — | 0.73 | ⬜ |
| 15 | Qu'est-ce qu'un produit ultra-transformé ? | À recopier depuis l'article téléchargé | « Les produits non transformés qui comprennent un seul ingrédient ou une seule catégorie d’ingrédients (par exemple fruits ou légumes frais, viandes crues découpées, miel…) Les produits transformés ayant, pour toute transformation, été soumis à une maturation, et qui comprennent un seul ingrédient ou une seule catégorie d’ingrédients NB : le produit visé est essentiellement la viande » [1] | — | — | — | 0.66 | ⬜ |

## Questions pièges (hors corpus)

| Question | Réponse obtenue | LLM appelé | Score | Résultat |
|---|---|---|---|---|
| Quelle est la recette de la blanquette de veau ? | « Mélanger avec une spatule en bois pour obtenir un mélange riche et homogène. Le mélanger au roux à l’aide d’un fouet. » [1] | non | 0.62 | ❌ le système a répondu |
| Quel est le meilleur régime pour perdre 10 kg en un mois ? | « Lisez aussi Surveillez le poids, indice de santé majeur, page 10 Alertez le médecin si le poids a varié de 2 kg ou plus dans le mois. k si la personne que vous aidez mange moins depuis plus de trois jours ; » [1] | non | 0.61 | ❌ le système a répondu |

## Sources retrouvées pour chaque question

Les 3 passages les plus proches (fichier — page ou section — score). Ils servent à remplir les colonnes « Fichier source » et « Page / section » de `docs/questions_validation.md`.

- **1.** [1] 244900_spf00001365.pdf — page 2 (0.81) ; [2] note_groupes_aliments.docx — section : Les fruits et légumes (0.81) ; [3] 42466_spf00000619.pdf — page 33 (0.77)
- **2.** [1] note_nutriscore.docx — section : Qu'est-ce que le Nutri-Score ? (0.63) ; [2] FAQ-updatedAlgo-FR_V11.pdf — page 44 (0.58) ; [3] note_nutriscore.docx — section : Le Nutri-Score expliqué simplement (0.58)
- **3.** [1] note_nutriscore.docx — section : Depuis quand existe-t-il en France ? (0.80) ; [2] FAQ-updatedAlgo-FR_V11.pdf — page 44 (0.75) ; [3] mars2025RU-FR-vf.pdf — page 1 (0.74)
- **4.** [1] 244900_spf00001365.pdf — page 1 (0.74) ; [2] NUT2012SA0103Ra-1.pdf — page 177 (0.71) ; [3] 42466_spf00000619.pdf — page 36 (0.67)
- **5.** [1] 42466_spf00000619.pdf — page 25 (0.86) ; [2] Augmenter l'activité physique _ Manger Bouger.html — section : La recommandation (0.84) ; [3] 42466_spf00000619.pdf — page 59 (0.83)
- **6.** [1] Aller vers les poissons gras et maigres en alternance _ Manger Bouger.html — section : La recommandation (0.78) ; [2] PNNS_4_2019-2023_cle4792b7.pdf — page 78 (0.67) ; [3] 174000565.pdf — page 410 (0.66)
- **7.** [1] spf00001656.pdf — page 58 (0.63) ; [2] NUT2012SA0103Ra-1.pdf — page 167 (0.63) ; [3] NUT2012SA0103Ra-1.pdf — page 167 (0.63)
- **8.** [1] 42466_spf00000619.pdf — page 36 (0.80) ; [2] 42466_spf00000619.pdf — page 50 (0.76) ; [3] note_groupes_aliments.docx — section : Tableau récapitulatif (0.70)
- **9.** [1] 174000565.pdf — page 423 (0.78) ; [2] note_chronologie.docx — section : Les grandes dates (0.78) ; [3] 174000565.pdf — page 425 (0.77)
- **10.** [1] 42466_spf00000619.pdf — page 35 (0.73) ; [2] 244900_spf00001365.pdf — page 3 (0.72) ; [3] 42466_spf00000619.pdf — page 35 (0.72)
- **11.** [1] 42466_spf00000619.pdf — page 59 (0.61) ; [2] 42466_spf00000619.pdf — page 23 (0.58) ; [3] 42466_spf00000619.pdf — page 25 (0.58)
- **12.** [1] PNNS_4_2019-2023_cle4792b7.pdf — page 35 (0.65) ; [2] mars2025RU-FR-vf.pdf — page 4 (0.54) ; [3] PNNS_4_2019-2023_cle4792b7.pdf — page 35 (0.53)
- **13.** [1] PNNS_4_2019-2023_cle4792b7.pdf — page 13 (0.74) ; [2] PNNS_4_2019-2023_cle4792b7.pdf — page 12 (0.72) ; [3] PNNS_4_2019-2023_cle4792b7.pdf — page 13 (0.71)
- **14.** [1] NUT2012SA0103Ra-1.pdf — page 168 (0.73) ; [2] NUT2012SA0103Ra-1.pdf — page 163 (0.69) ; [3] NUT2012SA0103Ra-1.pdf — page 99 (0.68)
- **15.** [1] FAQ-updatedAlgo-FR_V11.pdf — page 9 (0.66) ; [2] PNNS_4_2019-2023_cle4792b7.pdf — page 78 (0.52) ; [3] FAQ-updatedAlgo-FR_V11.pdf — page 40 (0.48)
