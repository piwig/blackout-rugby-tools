# BRT 2.12.1 — imports et récupération

Cette revue cherche les erreurs qui peuvent rester invisibles malgré des calculs arithmétiques corrects : conseiller à partir d’un ancien effectif ou annoncer qu’une restauration est valide alors qu’elle est incomplète.

## Défauts reproduits

Le parcours historique `/api/import` pouvait faire d’un effectif ancien le dernier effectif courant. Certains JSON datés recevaient la date d’import au lieu de celle de l’observation, faussant également la lecture de progression. Le correctif partage les règles chronologiques avec l’import par aperçu et contrôle le lot avant toute écriture. La revue indépendante a également reproduit puis vérifié la correction d’un ancien classeur qui remplaçait des consignes d’entraînement malgré des joueurs inchangés. Les anciens plannings absents restent ajoutables, sans écraser les plannings existants.

La sauvegarde pouvait créer une base SQLite vide si une source attendue avait disparu. Le vérificateur de restauration acceptait certaines archives incomplètes et ne vérifiait pas réellement le code conservé. Les contrôles exigent désormais les composants nécessaires et une archive exploitable ; les sources sont ouvertes en lecture seule.

## Validation

Les reproductions utilisent des données synthétiques, sans donnée de compte ni secret dans le dépôt. Les 30 tests ciblés de sauvegarde couvrent notamment sources absentes, WAL, schéma incomplet, publication atomique, rétention, gzip tronqué et assets manquants. La revue indépendante des imports a vérifié 98 tests ciblés, un oracle de 75 combinaisons d’offsets, l’isolation seniors/juniors et un rollback complet après une erreur injectée entre deux écritures.

Validation intégrée du 1er novembre 2026 : **1 293 tests Python et 203 tests Node réussis**, contrôle TypeScript et build Vite réussis, 3 646 clés de traduction cohérentes dans les quatre langues. Les empreintes des sources sont restées identiques pendant la validation. Le premier lancement Node a échoué sur l’alias Python Windows absent ; sa relance avec `BRT_TEST_PYTHON` pointant vers l’environnement du projet a réussi, sans modification applicative. L’avertissement de dépréciation Starlette/TestClient et celui de taille du bundle Vite restent présents.

Le 1er novembre 2026, un snapshot Restic réel a été restauré dans un répertoire temporaire du VPS et contrôlé par le nouveau vérificateur. Inventaire des espaces, intégrité et schéma SQLite, format des clés, archive des sources et du frontend, présence des configurations serveur : contrôles réussis. Le répertoire temporaire a ensuite été supprimé. Les données, références de comptes et résultats détaillés restent dans les preuves privées.

Une restauration isolée de données et de sources ne démontre pas à elle seule un redémarrage complet sur une nouvelle machine : les dépendances, le DNS, les accès externes et le service doivent aussi être reconfigurés. Aucun worker Classic n’est lancé pendant ce contrôle et aucune base de production n’est remplacée.

Un fichier réellement sans date garde le comportement compatible de l’ancien import : son heure d’import sert de repère, sans prouver la date des mesures. Le parcours avec aperçu permet de renseigner explicitement cette date. Une date au jour ne permet pas de départager deux relevés du même jour.

## Publication

La version **2.12.1** a été publiée le 1er novembre 2026 depuis le commit `67767e33a3fb5250d5603191ae49aeac5a27b1cd`. L’archive déployée a pour SHA-256 `e675a9eb11bed7667be186f8847add0e283a3e18c1e75154bcebe3cb9d8de676`. Une revue indépendante a rapproché 283 fichiers sources avec le manifeste testé, en tenant compte de la normalisation des fins de ligne du packaging, et les 30 fichiers statiques octet pour octet.

Après publication : service actif, santé/version attendues, intégrité et schémas SQLite vérifiés en lecture seule, volumes observés inchangés. Les 30 fichiers statiques servis correspondent à l’archive ; 48 accès à des routes privées sans session renvoient 401. Redirection HTTPS, en-têtes de sécurité et CAPTCHA actif contrôlés ; une connexion sans jeton CAPTCHA reçoit 403. Ces contrôles ne constituent pas un nouvel essai de connexion utilisateur avec résolution du CAPTCHA.

Les sauvegardes avant et après publication ont réussi. L’archive créée par le nouveau producteur a ensuite passé un contrôle isolé des données et des sources, sans démarrer l’application restaurée ni déchiffrer les identifiants. Cet examen complète l’exercice Restic réel décrit plus haut.

Une première installation a échoué parce que le script privé de transfert transmettait un masque de permissions trop restrictif à l’extraction. L’ancienne version a été retrouvée active et saine au contrôle. Le masque a été corrigé, puis la même archive a été installée dans un nouveau répertoire de version avant les vérifications finales ci-dessus. Les journaux intermédiaires sont conservés dans les preuves privées.
