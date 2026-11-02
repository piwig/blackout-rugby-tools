# BRT 2.13.2 — Feuilles contenant des internationaux

## Correction

Classic peut fournir `nat` et `u20` dans une fiche joueur avec un code pays. Ces appartenances à une sélection ne sont pas les sélecteurs de population de la requête. Jour de match les interprétait à tort comme des indicateurs de rencontre, ce qui bloquait la comparaison complète dès qu’un international figurait sur la feuille d’un club.

La lecture conserve les contrôles de population à la racine des réponses, sur la rencontre et les compositions. L’identité de chaque joueur demandé reste vérifiée. Le contrôle d’un éventuel sélecteur `youth` dans une fiche reste inchangé. Les appartenances nationales ne sont ni réinterprétées ni ajoutées aux statistiques.

## Vérification

Huit cas de non-régression couvrent le même amical lu depuis chaque équipe, pour les clubs seniors, juniors et les espaces U20 et nationaux. Des internationaux figurent dans les deux compositions. Les huit cas échouent avant la correction, puis passent avec les contrôles de population et d’identité existants. Un cas supplémentaire conserve le refus d’un sélecteur junior contradictoire.

La vérification réelle porte sur une rencontre de clubs, via des lectures publiques Classic. Les parcours U20 et nationaux sont couverts par des données synthétiques ; aucun accès réel à une sélection n’est revendiqué. Aucun changement de composition, de tactique ou de donnée importée n’est nécessaire.

Validation locale : 1 375 tests Python et 216 tests Node réussis, contrôle de 3 755 clés dans les quatre langues, TypeScript et build réussis. La revue indépendante ne relève aucun constat actionnable. Les avertissements existants concernent TestClient et la taille du bundle.
