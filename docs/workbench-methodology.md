# Atelier quotidien : données et limites

Le lot 2.1 complète les écrans existants, sans changer les droits sur Classic. Les nouveaux documents sont stockés dans le KV de chaque base privée, sous `workbench:`, `lineup_lab:` et `insights:`. Leurs mutations utilisent la session, la protection CSRF, une vérification du club et une révision transactionnelle (conflit HTTP 409). Ils sont inclus dans l’export par préfixes explicites ; les clés API et sessions restent exclues.

## Saisies, sauvegardes et conflits

Le planning d’entraînement, le XV, les dates du calendrier et les notes de joueurs distinguent le brouillon de la version enregistrée. Leurs champs sont bloqués pendant leur sauvegarde. Attendre la confirmation avant de quitter permet de connaître le résultat de l’opération ; en cas d’erreur, lire le message avant de reprendre ou de quitter la saisie.

Un changement de rubrique, de club ou une déconnexion demande confirmation si un de ces brouillons est modifié. Le changement de saison du planning, le changement d’onglet du XV et la fermeture d’une note protègent aussi leur saisie. Le navigateur peut afficher son propre avertissement lors d’un rechargement ou d’une fermeture. Ces protections ne constituent pas une sauvegarde automatique : les brouillons vivent dans l’écran ouvert et sont abandonnés si le départ est confirmé.

Une sauvegarde concurrente ne remplace pas silencieusement les changements d’un autre onglet. Le planning et le XV comparent la version lue, le calendrier contrôle sa révision et la note compare son texte et son suivi. L’étoile de suivi du tableau utilise aussi cette vérification. En cas de conflit, le brouillon reste visible. Relever les éléments à conserver avant d’utiliser le bouton de relecture : après confirmation, celui-ci remplace le brouillon par les données enregistrées. Les modifications souhaitées peuvent ensuite être reprises ; aucune fusion automatique n’est effectuée.

Dans les tableaux de l’académie et des seniors, la recherche accepte un nom ou une partie d’identifiant. Elle ignore les accents, la casse, les espaces en début ou fin et les espaces répétés. Le tri des compétences connues est numérique ; les valeurs sans niveau numérique, inconnues ou qualitatives B/M/H, restent à la fin dans les deux sens.

## Bien démarrer son club

La carte « Bien démarrer » de l’accueil propose sept repères : mentor, trésorerie, transferts, staff, stade, échéance économique, puis préparation du XV. Les cases « Pris en compte » et l’état replié sont enregistrés par club dans l’espace privé du manager, avec révision et protection contre les sauvegardes concurrentes. Une case est une déclaration du manager ; elle ne prouve ni ne réalise une action dans Classic. La carte reste accessible après avoir été repliée. Le chapitre du tutoriel explique le parcours et ses limites.

Source : conseils de Franck du 31 octobre 2026, et non règles officielles de l’éditeur. Le choix du mentor est libre. Les 300 000 unités virtuelles évoquent une dotation de départ, jamais le solde courant du club. Les conseils invitent à différer les achats de joueurs, à limiter le staff initial au recruteur de l’académie et au manager, sans adjoints, puis à préparer le stade avant l’équipe type. Le repère économique « mardi minuit » doit être vérifié dans le calendrier et le fuseau du jeu ; aucune échéance datée n’en est créée automatiquement.

## Compositions

Le laboratoire conserve des postes verrouillés, titulaires imposés et exclusions. Les choix contradictoires ou indisponibles sont rejetés. Le XV maximise l’affectation calculable puis l’indice local, avec unicité. Le banc privilégie la couverture des rôles : une affinité est retenue si elle atteint 80 % de la meilleure affinité du joueur ; deux options pilier et une par autre rôle sont recherchées. Un joueur pouvant couvrir plusieurs rôles ne peut pas tous les remplacer simultanément. Cette méthode ne certifie ni qualification de première ligne ni remplacements réglementaires.

Les scénarios enregistrent leurs options et l’observation datée, jamais des secrets. Des objectifs ou sources différents empêchent d’afficher un gain de score comme comparable. L’application locale recalcule et protège la version de l’effectif et la composition enregistrée, dans une transaction. Rien n’est transmis à Classic par le laboratoire.

## Calendrier et alertes

Les dates conservent leur décalage et le fuseau de saisie. Les heures locales inexistantes lors d’un changement d’heure sont refusées. L’import de rencontres est explicite et limité aux données lisibles de Classic. Une référence à un joueur disparu reste signalée et peut être retirée progressivement ; aucune nouvelle référence inconnue n’est acceptée. Les intentions de rotation ne prédisent pas l’énergie future.

Les préférences choisissent les catégories, horizon, ancienneté et format d’énergie. Les notes/suivis seniors et académie ont des destinations distinctes. Les notifications du navigateur ne sont pas un service de push en arrière-plan : elles nécessitent une autorisation explicite et le cockpit ouvert. Au plus trois alertes nouvelles sont affichées par actualisation, avec déduplication en mémoire. Le bilan vacances est limité au journal réellement retenu et ne prétend pas être exhaustif.

## Académie et adversaires

L’académie examine au plus 240 instantanés et 500 changements, avec indication de troncature. Les valeurs inconnues restent inconnues. Une compétence dévoilée est distincte d’une variation numérique. Les observations au même instant sont regroupées avant le calcul : des valeurs contradictoires sont signalées et ne fournissent pas une progression ou une base arbitraire. Les séances sont des déclarations manuelles datées, rapprochées du planning actuel, sans causalité attribuée.

Dans **Séances planifiées et réalisées**, les créneaux proposés proviennent des cases renseignées du planning, avec filtres de saison et de semaine. **Déclarer la séance** reprend uniquement la saison, la semaine, le créneau et la compétence prévue. La date réelle reste vide et obligatoire ; elle n’est jamais calculée à partir du planning. Le manager vérifie la compétence réalisée et enregistre la déclaration. Une déclaration pour une même saison, semaine et créneau remplace la précédente ; rien n’est déclaré automatiquement ni transmis à Classic. L’absence de déclaration ne prouve pas l’absence d’entraînement, et le dernier export ne reconstitue pas les séances passées.

Les matchs sont identifiés par leur type et numéro ; leur côté, adversaire et club sont associés explicitement. Les agrégats affichent rencontres, actions classées et couverture. Une bibliothèque privée ne devient pas une source appartenant automatiquement au club sélectionné. Les scripts historiques absents de Franck restent nécessaires pour certifier une équivalence avec ses anciennes analyses.

La matrice des dossiers adversaires croise les quatre zones relatives à l’adversaire (`22`, `40`, `40A`, `22A`) et cinq types d’attaque. Elle respecte les filtres de dossier, saison, type de match et côté du club. Chaque cellule affiche le nombre d’actions et `100 × nombre / actions adverses classées de la zone` ; le total de cette zone figure en dernière colonne. Une zone vide affiche « Aucune observation » et des tirets, sans pourcentage. La couverture générale a un autre dénominateur : tous les événements des rencontres retenues, des deux côtés. Ces volumes décrivent les observations classées, sans prédiction tactique.

## Stade et retours

Les coûts unitaires, capacités cibles, trésorerie et réserve sont renseignés ou repris des données connues. Une donnée manquante laisse le total indisponible. Les réductions de capacité ne créent aucun revenu supposé. Un brouillon intact suit une actualisation du club ; un brouillon modifié conserve les choix et signale la nouvelle source, avec reprise explicite possible.

L’aide « Répartir une capacité totale » reprend les proportions existantes du modèle de Franck : debout 22 %, assis découvert 39 %, assis couvert 30 %, abonnés 8 %, loges 1 %. Elle complète le simulateur historique, dont le multiplicateur initial reste neuf fois le nombre de membres. Le manager saisit lui-même le total : il n’est pas déduit d’une capacité ou d’un nombre de membres inconnu. L’arrondi part du plancher de chaque catégorie puis distribue les places restantes aux plus grands restes ; les égalités suivent l’ordre des catégories affichées. La somme est exactement le total saisi. La saisie accepte un entier de 0 à 2 564 103, ce qui maintient chaque catégorie dans la limite d’un million de places ; un champ vide ou invalide ne produit aucune cible.

La saisie du total affiche seulement un aperçu. Le bouton « Remplacer les cinq capacités cibles » applique explicitement les cinq valeurs au brouillon, en conservant les capacités actuelles, tarifs, trésorerie, réserve et notes. L’enregistrement du scénario reste une étape distincte. Les coûts, frais annexes et la réserve sont à vérifier dans le devis réel de Classic ; tous les montants sont virtuels. Aucun calcul ne lance de construction et aucune donnée absente n’est convertie en zéro observé.

Le simulateur fondé sur les membres applique lui aussi les plus grands restes, après un unique arrondi décimal de la capacité totale (demi-place arrondie vers le haut). Il utilise donc la même répartition que le serveur et le scénario à capacité totale identique ; les cibles des cinq tribunes ne sont plus arrondies indépendamment.

Les palettes et blasons sont construits depuis des choix bornés, sans HTML/SVG utilisateur. Depuis la version 2.12.2, le formulaire de retour par écran est retiré de l’interface ; le parcours **Contact & idées** reste disponible. Les anciens retours restent conservés dans les données privées et leurs API gardent les règles de confidentialité : partage administrateur explicite, liste blanche de champs et modification limitée aux retours partagés.
