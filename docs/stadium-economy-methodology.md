# Stade : économie prévisionnelle BRT v1

Ce module compare des hypothèses personnelles de club en monnaie virtuelle. Il ne contient aucun tarif présumé, ne prévoit pas la fréquentation du jeu et ne transmet aucune instruction à Classic. Les sélections et les juniors ne possèdent pas de scénario financier de club.

Chaque scénario conserve deux options, « situation actuelle » et « projet », et un horizon explicite : nombre de matchs à domicile et nombre de semaines. Les cinq tribunes sont `standing`, `uncovered`, `covered`, `members`, `corporate`. Chaque option contient sa source et sa date d’hypothèse, puis capacité, prix, remplissage et coût variable par spectateur pour chaque tribune. Les recettes et coûts annexes comportent chacun une composante par spectateur et une composante fixe par match. Les autres charges fixes par match et l’entretien par semaine restent séparés.

Un champ vide signifie inconnu ; zéro signifie une hypothèse nulle explicitement saisie. Les coûts, prix et remplissages manquants bloquent les résultats concernés. Une tribune explicitement de capacité zéro n’exige pas de tarif, de taux ou de coût variable. Source et date manquantes bloquent le résultat par match. Un entretien ou un horizon manquant bloque la projection, sans effacer un net par match calculable. L’investissement inconnu bloque la trésorerie après investissement et les indicateurs qui en dépendent.

Les capacités importées sont proposées uniquement lorsque les métadonnées contiennent une provenance explicite `stadium_source` et une date ISO `stadium_observed_on`, avec des capacités entières valides. Les nouvelles lectures de club Classic (import du compte manager et actualisation du club) enregistrent ces deux champs si elles contiennent au moins une capacité de tribune. Les chaînes numériques entières retournées par Classic sont converties sans perte ; les décimaux, booléens et capacités hors limites sont refusés. Les métadonnées historiques ordinaires contenant seulement `date_maj` ne suffisent pas à garantir cette provenance ; la saisie reste alors vide. Aucun tarif ni coût n’est initialisé automatiquement. La réponse de sauvegarde inclut les mêmes capacités initiales que la lecture ; le client les conserve également lorsqu’un ancien serveur ne les renvoie pas, afin qu’une création après sauvegarde garde ce point de départ.

## Entrées et flux

Pour chaque tribune, entrées = partie entière inférieure de (capacité × remplissage / 100). Les entrées ne peuvent pas dépasser la capacité. Les calculs internes utilisent `Decimal` sans arrondi monétaire intermédiaire, dans un contexte local de précision 60 couvrant les bornes déclarées, y compris les pourcentages de rendement extrêmes ; les montants affichés sont arrondis au centième, demi supérieur. Une somme de montants déjà affichés peut donc différer d’un centième du total calculé avant arrondi. Les paramètres monétaires acceptent au maximum quatre décimales, de 0 à 10¹² ; les capacités sont entières, de 0 à 10⁷ par tribune ; les taux vont de 0 à 100 % ; les horizons sont des entiers de 0 à 10 000. Booléens, valeurs infinies, NaN, montants négatifs et champs inconnus sont refusés.

- Billetterie = somme des entrées par tribune × prix correspondant.
- Recettes annexes = entrées totales × recettes annexes par spectateur + recettes annexes fixes.
- Charges par match = somme des entrées × coûts variables par tribune + entrées totales × coûts annexes par spectateur + coûts annexes fixes + autres charges fixes.
- Net par match = billetterie + recettes annexes − charges par match.
- Net de la projection = net par match × nombre de matchs − entretien hebdomadaire × nombre de semaines.
- Trésorerie après investissement = net de la projection − nouvelles dépenses prévues.

L’investissement est une dépense ponctuelle **future** propre à chaque option. Les dépenses déjà engagées ne sont pas reprises. La situation actuelle doit également indiquer explicitement zéro investissement lorsqu’aucun nouveau financement n’y est prévu. Les charges hebdomadaires sont déduites une seule fois par semaine et jamais multipliées à nouveau par les matchs. La projection est un flux prévisionnel, pas un solde bancaire ni une recette encaissée.

La ligne personnalisée respecte les taux de chaque tribune. Les six lignes 50, 60, 70, 80, 90 et 100 % remplacent tous ces taux par un même taux. Elles ne modifient pas le scénario enregistré.

## Comparaison, seuil et récupération

Le seuil par match recherche le **premier** taux uniforme pour lequel le net par match est positif ou nul, sur une grille exhaustive de 0 à 100 % par pas de 0,01 %. Il respecte les arrondis d’entrées et exclut l’entretien hebdomadaire et les investissements. « Non atteint » signifie aucun taux satisfaisant sur cette grille, « données insuffisantes » signifie que les hypothèses nécessaires sont inconnues. Ce seuil n’est pas un taux de fréquentation prévu. En présence de marges négatives dans certaines tribunes, le net n’est pas nécessairement monotone : les taux supérieurs au premier seuil ne garantissent pas tous un résultat positif. La précision du seuil est limitée à la grille annoncée.

Gain supplémentaire = net de la projection du projet − net de la projection actuelle. Investissement supplémentaire = nouvelles dépenses prévues du projet − celles de la situation actuelle. Gain moyen par match = gain supplémentaire / nombre de matchs, pour un nombre de matchs strictement positif. Cette moyenne inclut donc une seule fois la différence d’entretien sur l’horizon déclaré.

La récupération n’est calculée que si le gain supplémentaire moyen est connu et strictement positif, et si les deux investissements sont connus. Matchs de récupération = max(0, investissement supplémentaire) / gain moyen par match. Un investissement supplémentaire nul ou négatif donne une récupération de zéro dans ce cas ; un gain nul, négatif ou inconnu ne produit aucune récupération. Prolonger cette moyenne suppose de conserver le même rapport semaines/matchs et les mêmes hypothèses ; ce n’est aucune garantie de résultat futur.

Le rendement de l’horizon vaut (gain supplémentaire − investissement supplémentaire) / investissement supplémentaire × 100. Il est présenté uniquement pour un gain supplémentaire et un investissement supplémentaire strictement positifs et connus. Il peut être négatif avant récupération. Un investissement nul ne donne aucun pourcentage de rendement. Tous ces indicateurs comparent les deux options ; le bénéfice total du stade n’est pas confondu avec le bénéfice supplémentaire des travaux.

## Persistance et intégration

`register_stadium_economy(app, store, auth, require_team)` expose `GET/POST /api/stadium-economy`, `GET /api/stadium-economy/export` et `POST /api/stadium-economy/calculate`. Les lectures et exports demandent `team_id` et acceptent uniquement `context=club`. Le calcul reçoit `{team_id, context: "club", scenario}` et ne sauvegarde rien. Une sauvegarde reçoit `{team_id, context: "club", expected_revision, scenarios}`. Les documents sont isolés par compte avec le store privé existant, puis par club dans `stadium_economy:<team_id>`.

La sauvegarde remplace atomiquement les scénarios du club (50 maximum, identifiants uniques) sous transaction `BEGIN IMMEDIATE` et contrôle de révision. Une révision périmée donne HTTP 409 ; le brouillon client est conservé. Une équipe détachée est revérifiée sous verrou d’écriture. Authentification, autorisation d’équipe et CSRF sont celles du produit. L’export JSON conserve les hypothèses nulles et la provenance, sans y mélanger de secrets ni de réponse calculée. L’interface permet création, édition, duplication, suppression du brouillon, sauvegarde, relecture et export des scénarios enregistrés. Elle avertit avant abandon des modifications, protège la navigation et ignore les réponses tardives après changement de session ou de club. Les résultats affichés sont invalidés à chaque modification des hypothèses.

Le composant React `StadiumEconomy(Actions)` s’intègre dans « Stade & finances ». Les anciennes fonctions de capacité et de budget de construction restent indépendantes.

La saisie présente d’abord la situation actuelle. Le projet est replié dans une section que le manager ouvre pour le comparer ; le bouton de copie depuis la situation actuelle précède cette section et demande confirmation avant tout remplacement. La copie conserve les inconnues et duplique les données : une modification ultérieure du projet ne modifie pas l’actuel. Les recettes annexes, charges et investissement sont également regroupés dans des sections repliables dont le titre rappelle que les hypothèses manquantes doivent être renseignées ; les replier n’ajoute aucune valeur nulle et ne dispense d’aucune donnée nécessaire au calcul.
