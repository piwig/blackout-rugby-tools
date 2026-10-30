# Atelier quotidien : données et limites

Le lot 2.1 complète les écrans existants, sans changer les droits sur Classic. Les nouveaux documents sont stockés dans le KV de chaque base privée, sous `workbench:`, `lineup_lab:` et `insights:`. Leurs mutations utilisent la session, la protection CSRF, une vérification du club et une révision transactionnelle (conflit HTTP 409). Ils sont inclus dans l’export par préfixes explicites ; les clés API et sessions restent exclues.

## Compositions

Le laboratoire conserve des postes verrouillés, titulaires imposés et exclusions. Les choix contradictoires ou indisponibles sont rejetés. Le XV maximise l’affectation calculable puis l’indice local, avec unicité. Le banc privilégie la couverture des rôles : une affinité est retenue si elle atteint 80 % de la meilleure affinité du joueur ; deux options pilier et une par autre rôle sont recherchées. Un joueur pouvant couvrir plusieurs rôles ne peut pas tous les remplacer simultanément. Cette méthode ne certifie ni qualification de première ligne ni remplacements réglementaires.

Les scénarios enregistrent leurs options et l’observation datée, jamais des secrets. Des objectifs ou sources différents empêchent d’afficher un gain de score comme comparable. L’application locale recalcule et protège la version de l’effectif et la composition enregistrée, dans une transaction. Rien n’est transmis à Classic par le laboratoire.

## Calendrier et alertes

Les dates conservent leur décalage et le fuseau de saisie. Les heures locales inexistantes lors d’un changement d’heure sont refusées. L’import de rencontres est explicite et limité aux données lisibles de Classic. Une référence à un joueur disparu reste signalée et peut être retirée progressivement ; aucune nouvelle référence inconnue n’est acceptée. Les intentions de rotation ne prédisent pas l’énergie future.

Les préférences choisissent les catégories, horizon, ancienneté et format d’énergie. Les notes/suivis seniors et académie ont des destinations distinctes. Les notifications du navigateur ne sont pas un service de push en arrière-plan : elles nécessitent une autorisation explicite et le cockpit ouvert. Au plus trois alertes nouvelles sont affichées par actualisation, avec déduplication en mémoire. Le bilan vacances est limité au journal réellement retenu et ne prétend pas être exhaustif.

## Académie et adversaires

L’académie examine au plus 240 instantanés et 500 changements, avec indication de troncature. Les valeurs inconnues restent inconnues. Une compétence dévoilée est distincte d’une variation numérique. Les observations au même instant sont regroupées avant le calcul : des valeurs contradictoires sont signalées et ne fournissent pas une progression ou une base arbitraire. Les séances sont des déclarations manuelles datées, rapprochées du planning actuel, sans causalité attribuée.

Les matchs sont identifiés par leur type et numéro ; leur côté, adversaire et club sont associés explicitement. Les agrégats affichent rencontres, actions classées et couverture. Une bibliothèque privée ne devient pas une source appartenant automatiquement au club sélectionné. Les scripts historiques absents de Franck restent nécessaires pour certifier une équivalence avec ses anciennes analyses.

## Stade et retours

Les coûts unitaires, capacités cibles, trésorerie et réserve sont renseignés ou repris des données connues. Une donnée manquante laisse le total indisponible. Les réductions de capacité ne créent aucun revenu supposé. Un brouillon intact suit une actualisation du club ; un brouillon modifié conserve les choix et signale la nouvelle source, avec reprise explicite possible.

Les palettes et blasons sont construits depuis des choix bornés, sans HTML/SVG utilisateur. Les retours privés restent privés. Le partage administrateur est un choix explicite ; sa vue emploie une liste blanche de champs, et seules les révisions des retours partagés peuvent y être changées.
