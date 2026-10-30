# Méthodologie du centre d’optimisation

Le centre prépare des décisions à partir des observations privées du manager. Le moteur est déterministe, sans dépendance externe et sans action dans Blackout Rugby. Il ne simule ni résultats, ni entraînement, ni récupération. L’aperçu ne modifie aucune composition ni aucun programme enregistré. La sauvegarde locale passe par une action explicite dans l’interface.

Les sauvegardes de l’aperçu peuvent fournir `expected_grid` à `/api/plans` ou `expected_slots` à `/api/lineup`. Le serveur compare cette observation à la valeur actuelle et écrit dans une même transaction SQLite réservée avant la lecture. Si un autre onglet ou une autre session l’a modifiée entre-temps, la réponse 409 demande de recharger puis recalculer ; la valeur plus récente reste intacte. Un plan absent est comparé à une grille vide 4 × 16 et une composition absente à `{}`. Les écrans historiques qui omettent ces champs conservent leur comportement de sauvegarde.

## Périmètre privé et contrat

`GET /api/optimization` exige une session authentifiée et renvoie `{reports: [...]}`. Paramètres :

- `team_id` : identifiant du club. Un identifiant explicitement demandé mais absent du store courant renvoie 404 ; aucun repli silencieux vers un autre club.
- `scope=current|all` : club choisi ou clubs connus du seul espace privé du manager.
- `objective=balanced|recovery|development` : objectif de composition.
- `energy_floor` : seuil inclusif de 0 à 110 %, 60 par défaut.
- `energy_scale=auto|percent|level` : interprétation des observations d’énergie, `auto` par défaut.
- `season` : saison de 1 à 999. Sans choix, la dernière saison importée est utilisée ; si elle est absente, la valeur technique 1 ne déclenche aucun ajout au planning, et l’horizon est signalé inconnu.

Paramètres invalides : 422. Sans club enregistré, la liste des bilans est vide. Aucun accès aux clés API n’est inclus dans la réponse. Tous les calculs d’une requête partagent la même date UTC de génération.

## Données connues et disponibilité

Les compétences masquées (`Unknown`, `Low`, `Medium`, `High`) et les absences ne deviennent jamais zéro. Zéro numérique demeure une observation valide. Une affinité de rôle existe seulement si toutes ses compétences pondérées sont connues. Les identifiants répétés sont dédupliqués avec avertissement ; seule leur première observation est conservée.

La [documentation officielle de l’API Classic, ressource joueurs](https://www.blackoutrugby.com/game/help.documentation.php?category=35&question=329), vérifiée le 30 octobre 2026, distingue l’énergie Premium en pourcentage de 0 à 110 et l’énergie non Premium en niveaux de 1 à 11. Le moteur applique les règles suivantes :

- `percent` conserve les mesures de 0 à 110 ; les valeurs hors plage sont inconnues.
- `level` convertit les niveaux entiers 1 à 11 en `niveau × 10` pour appliquer seuil et bonus. Cette approximation est signalée avec la valeur brute ; elle ne reconstitue pas une mesure précise.
- `auto` retient le pourcentage lorsqu’au moins une mesure exploitable du club dépasse 11. Si toutes les observations sont inférieures ou égales à 11, l’échelle reste ambiguë : ni filtre, ni bonus d’énergie ne s’applique, et les énergies calculées sont nulles. Le manager peut choisir l’échelle explicitement. Un export mêlant plusieurs formats nécessite une vérification manuelle.

Une énergie connue strictement inférieure au seuil exclut le joueur. Une énergie inconnue autorise un candidat sous réserve, avec avertissement, sans lui inventer un niveau ni un bonus.

La blessure Classic représente une date de fin : un timestamp Unix numérique supérieur à 1, ou une date ISO avec décalage horaire, est comparé à la date UTC du bilan. Une date future exclut le joueur ; une date passée ou égale ne l’exclut pas. La sentinelle `-001-11-30` indique l’absence de blessure. Les marqueurs explicites `1`, `True`, `oui`, `yes`, `injured` excluent ; `0`, `False`, `non`, `no` ne l’excluent pas. Une valeur absente, ambiguë ou une date sans fuseau ne confirme pas la disponibilité et reste signalée. La date de jeu importée ne sert pas d’horloge médicale actuelle.

## Composition du XV et banc

Les affinités reprennent les moyennes pondérées existantes du projet :

| Rôle | Compétences et poids |
| --- | --- |
| Pilier | Force 3, Technique 2, Endurance 1 |
| Talonneur | Dextérité 2, Force 2, Technique 2 |
| Deuxième ligne | Saut 3, Force 2, Technique 1 |
| Troisième ligne | Défense 2, Technique 2, Endurance 1, Force 1 |
| Demi de mêlée | Dextérité 3, Agilité 2, Jeu au pied 1 |
| Demi d’ouverture | Dextérité 2, Jeu au pied 2, Attaque 2 |
| Centre | Attaque 2, Défense 2, Force 1, Vitesse 1 |
| Ailier | Vitesse 3, Agilité 2, Attaque 1 |
| Arrière | Jeu au pied 2, Vitesse 2, Dextérité 2 |

Chaque somme est divisée par la somme des poids. Les objectifs ajoutent des bonus locaux, qui ne sont pas des règles officielles :

- Équilibre : affinité seule.
- Récupération : affinité + `3 × énergie / 110`, uniquement si l’énergie est interprétable.
- Développement : affinité + 3 jusqu’à 21 ans inclus ; bonus `(30 − âge) / 3` entre 21 et 30 ans ; zéro au-delà. Aucun bonus si l’âge est inconnu ou invalide.

Les scores sont arrondis à deux décimales. L’algorithme hongrois maximise d’abord le nombre de postes calculables, puis la somme de leurs scores. Il trouve une affectation globale exacte en temps polynomial, au lieu de choisir le meilleur joueur de chaque poste successivement. Chaque joueur ne peut être sélectionné qu’une fois. Les postes sans candidat restent vides. Les égalités utilisent l’ordre stable des identifiants.

Les huit réserves au maximum privilégient désormais la couverture indicative des rôles : une affinité atteint au moins 80 % de la meilleure du joueur ; deux options pilier et une par autre rôle sont recherchées. Les rôles manquants restent affichés. Cette couverture ne certifie ni qualifications de première ligne ni remplacements simultanés. Voir docs/workbench-methodology.md pour le laboratoire, les verrouillages et les scénarios.

La comparaison au XV sauvegardé est disponible seulement si les deux XV comportent 15 postes, chacun doté d’un joueur distinct, éligible selon les mêmes critères et calculable pour ce rôle. Autrement, les deux scores de comparaison et leur différence sont `null`. Un gain de score signifie uniquement une hausse de cet indice local.

## Académie et programme de saison

Le planning 4 × 16 concerne l’académie. Pour chaque compétence, le moteur calcule la moyenne des seules mesures connues et affiche le nombre de jeunes observés sur l’effectif. Les moyennes les plus basses guident la priorité ; une compétence absente de tous les jeunes n’est pas classée. Si une moyenne repose sur moins de la moitié des jeunes, l’aperçu signale que la priorité est provisoire. Ces moyennes ne corrigent pas les biais de dévoilement et ne prédisent aucune progression.

Le programme alterne les quatre priorités connues les plus basses, ou les priorités disponibles s’il y en a moins. Seules les cases libres de la semaine importée et des semaines suivantes peuvent être proposées. Toutes les cases existantes sont préservées, y compris dans les semaines futures ; toutes les semaines passées sont préservées, y compris leurs cases vides.

Pour une saison future par rapport à la dernière date importée, l’horizon commence à la semaine 1 ; pour la saison observée, il commence à sa semaine ; pour une saison passée ou une date invalide, aucun ajout n’est proposé. Sans compétence connue à l’académie, aucun entraînement n’est inventé. Le planning ne suppose aucun calendrier réel de compétition. Les phases de saison organisent les vérifications du manager et s’adaptent à l’objectif sélectionné.

## Matchs : observations et pistes de préparation

Les matchs appartiennent à la bibliothèque privée du manager. Aucune correspondance entre cette bibliothèque et le club du bilan n’est présumée. Les deux côtés sont analysés séparément.

La couverture vaut `100 × événements classés / tous les événements`. Les comptes bruts sont affichés, ainsi que le nombre d’événements marqués comme inférés depuis les commentaires. Ce dernier compte n’est pas assimilé à une observation indépendante certaine.

Une tendance exige au moins 60 % de couverture et 20 actions classées pour le côté étudié. Une attaque est dite dominante seulement si elle représente au moins 50 % de ces actions. Avec des données insuffisantes, aucune dominante ni piste de style n’est fournie. Ces seuils sont des règles de prudence locales, pas un test de significativité statistique.

Si ces critères sont satisfaits, une piste concrète de préparation accompagne la description : examiner Vitesse/Agilité/Défense des arrières face à une dominante Large ; Force/Technique/Défense du pack pour Percussion ou Pick and go ; Dextérité/Attaque du soutien pour Créatif ; Jeu au pied et couverture arrière pour le jeu au pied. Ces pistes demandent de revoir les séquences et plusieurs matchs ; elles ne démontrent aucun contre tactique efficace. La zone relative la plus observée est accompagnée de son compte sur les actions classées. Aucune causalité avec le résultat du match n’est affirmée.

## Stade, fraîcheur et limites

Un scénario de stade n’est proposé que si le nombre de membres et les cinq catégories de places sont connus et non négatifs. Il reprend le scénario existant de neuf places par membre avec les ratios 22/39/30/8/1 %. Il n’est ni une prévision d’affluence ni une instruction de construire. La date de la source, les coûts, l’affluence et la trésorerie du jeu restent à vérifier.

Un instantané âgé de plus de sept jours, sans date ou avec date incohérente produit un avertissement. La date d’importation ne garantit pas la fraîcheur des mesures d’un ancien export. Chaque horizon de saison rappelle la dernière date de jeu importée. Un nouvel import peut changer les candidats, les priorités et les conseils ; chaque aperçu doit être relu avant sa sauvegarde locale.

## Progression observée et calculs d’optimisation

La rubrique **Progression**, ajoutée au lot parcours du 30 octobre 2026, est une lecture indépendante de l’historique privé. Elle ne trace pas les scores d’affinité du moteur et ne transforme pas un programme proposé en résultat acquis. L’API `GET /api/progression?team_id=…` vérifie le club dans l’espace authentifié, puis sépare les observations des seniors et de l’académie. Elle ne réalise aucune écriture dans Classic.

Les compétences et le CSR proviennent des instantanés conservés. Les dates d’observation, sources, précisions de date et nombres de joueurs renseignés sont exposés avec les points. Le tri utilise UTC ; les anciennes dates sans fuseau sont interprétées en UTC pour le classement, en conservant leur précision d’origine. Une date calendaire ne permet pas de départager deux relevés dans la même journée. Les dates invalides sont écartées et dénombrées ; une source illisible ou trop volumineuse interrompt les comparaisons.

Une valeur inconnue reste `null`, y compris lorsqu’un import contient un texte de niveau masqué. Le passage d’inconnu à connu est un **dévoilement** et ne reçoit aucun delta numérique. Un joueur absent d’une observation crée une interruption. Deux observations contradictoires au même instant ne sont pas départagées par l’ordre d’insertion ; les contradictions sont conservées comme telles. Une seule observation donne un repère, sans progression mesurée.

La moyenne collective porte uniquement sur les mesures connues. Une variation collective n’est calculée que si les deux dates ont un effectif et un ensemble de joueurs renseignés comparables, sans contradiction, troncation ni ambiguïté d’ordre dans la journée. Les entrées et sorties d’effectif, changements de couverture et dénominateurs restent visibles. Une hausse de moyenne due à un nouveau joueur ou à une compétence dévoilée n’est donc pas présentée comme un gain d’entraînement.

La lecture est bornée par population à **240 instantanés récents**, **300 joueurs détaillés par date** et **12 000 présences joueur détaillées**. Un contenu d’instantané supérieur à **250 000 octets** n’est pas chargé dans les séries. Si la limite coupe un groupe de même instant, le groupe incomplet est écarté ; les budgets conservent des dates entières. L’interface indique les données omises, les dates couvertes et les nombres d’instantanés conservés et exploitables. Lorsque l’effectif est tronqué, les moyennes et variations collectives de ces dates sont indisponibles ; un effectif affiché avec `≥` est une borne minimale.

Les courbes ne comblent pas les valeurs manquantes et disposent d’un tableau des mêmes données. L’ingestion peut dédupliquer des instantanés inchangés : l’absence d’un nouveau point ne démontre ni absence d’activité ni absence d’entraînement. Une variation mesurée ne prouve pas sa cause et ne prédit aucun résultat futur. Les contrôles de parcours et leurs limites figurent dans le [rapport du lot](experience-2026-10-30.md).
