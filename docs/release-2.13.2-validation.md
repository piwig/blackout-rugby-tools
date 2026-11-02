# BRT 2.13.2 — Feuilles contenant des internationaux

## Correction

Classic peut fournir `nat` et `u20` dans une fiche joueur avec un code pays. Ces appartenances à une sélection ne sont pas les sélecteurs de population de la requête. Jour de match les interprétait à tort comme des indicateurs de rencontre, ce qui bloquait la comparaison complète dès qu’un international figurait sur la feuille d’un club.

La lecture conserve les contrôles de population à la racine des réponses, sur la rencontre et les compositions. L’identité de chaque joueur demandé reste vérifiée. Le contrôle d’un éventuel sélecteur `youth` dans une fiche reste inchangé. Les appartenances nationales ne sont ni réinterprétées ni ajoutées aux statistiques.

## Vérification

Huit cas de non-régression couvrent le même amical lu depuis chaque équipe, pour les clubs seniors, juniors et les espaces U20 et nationaux. Des internationaux figurent dans les deux compositions. Les huit cas échouent avant la correction, puis passent avec les contrôles de population et d’identité existants. Un cas supplémentaire conserve le refus d’un sélecteur junior contradictoire.

La vérification réelle porte sur une rencontre de clubs, via des lectures publiques Classic. Les parcours U20 et nationaux sont couverts par des données synthétiques ; aucun accès réel à une sélection n’est revendiqué. Aucun changement de composition, de tactique ou de donnée importée n’est nécessaire.

Validation locale : 1 375 tests Python et 216 tests Node réussis, contrôle de 3 755 clés dans les quatre langues, TypeScript et build réussis. La revue indépendante ne relève aucun constat actionnable. Les avertissements existants concernent TestClient et la taille du bundle.

## Publication vérifiée

Code publié le 2 novembre 2026 depuis `9bef9d5844e8ea82ff7798a7c66b5582ab224ca1`, archive SHA-256 `dbb1fd3c8dba43519c2d8f8cc52fc0e5c50d8d0d3b780ab92846c06d687bd8ee`. Le service redémarré annonce 2.13.2 ; sauvegardes avant et après réussies, intégrité des bases et volumes observés inchangés. Les 30 fichiers statiques correspondent à l’archive, les 50 accès privés testés sans session renvoient 401 et le CAPTCHA reste actif.

Après publication, la même rencontre réelle a été relue depuis ses deux clubs : les deux feuilles sont disponibles avec 23 joueurs identifiés chacune. Un contrôle connecté du parcours calendrier puis comparaison a aussi confirmé le chargement du rapport et ses 23 paires, sans erreur du formulaire. Une feuille adverse non fournie reste signalée explicitement ; aucun joueur manquant n’est inventé. Aucun ordre de jeu ni nouveau pilote d’écriture n’a été activé.
