# BRT 2.13.0 — Jour de match

La vue **Préparer le match → Jour de match** compare les deux feuilles Classic, du XV au banc, sur ordinateur et téléphone. Les capitaines et buteurs sont identifiés ; les indicateurs couvrent gabarit, CSR, forme, énergie, expérience, agressivité et discipline. Dix groupes permettent une lecture par ligne et par effectif.

## Calculs et données manquantes

Chaque poste conserve sa place lorsque Classic omet une fiche. Les moyennes affichent le nombre de valeurs connues ; un poids total exige tous les poids du groupe. Une absence n’est jamais transformée en zéro.

L’indice personnel est calculé en décimal : `CSR × (1 + 0,07 × (forme − 7)) × (1 + 0,02 × (expérience − 7)) × énergiePourcent / 100`. Le résultat est tronqué par joueur avant la moyenne entière. Des tests de référence couvrent les résultats entiers exacts qui étaient sous-évalués d’une unité par les flottants binaires. Cet indice n’est ni une mesure officielle ni un pronostic.

En mode automatique, une énergie supérieure à 11 établit le format pourcentage pour ce joueur seulement. Entre 0 et 11, le format reste inconnu. Le choix explicite du niveau applique l’approximation niveau × 10. Les pourcentages peuvent atteindre 110 ; valeurs non finies, booléens et attributs hors plage restent inconnus.

## Adaptation à Classic

Les lectures utilisent les contextes seniors, juniors, U20 et nationaux, avec vérification des identifiants et des marqueurs de population présents dans les documents et leurs lignes. Les noms juniors relèvent de l’espace club. Aucune feuille Default n’est substituée à une rencontre demandée.

Les essais réels ont établi deux particularités : Classic peut refuser une feuille absente plutôt que renvoyer une liste vide ; la requête de calendrier junior peut échouer côté serveur. Le premier cas laisse l’autre feuille consultable avec une explication. Dans le second, BRT vérifie au plus 50 identifiants de championnat issus du calendrier du club, avec le paramètre junior, puis présente une liste explicitement partielle. Une rencontre senior n’est jamais renommée junior sans confirmation.

Les échéances avec fuseau fournies par Classic sont distinctes des repères calculés H−3h05, H−3h et H−2h05. Une date ambiguë reste inconnue. Les caractéristiques correspondent au moment de la lecture, y compris pour un ancien match.

## Validation

Validation finale du 2 novembre 2026 : **1 357 tests Python et 211 tests Node réussis**, TypeScript et build Vite réussis, **3 737 clés cohérentes** en français, anglais, espagnol et italien. Les tests couvrent notamment permissions, CSRF, isolation des espaces, quatre populations, lectures bornées, positions manquantes, refus de lecture, repli junior, calculs et réponse tardive après changement de contexte.

Une revue indépendante a relevé les contrôles manquants sur les marqueurs de population racine, l’arrondi décimal et les associations accessibles entre chiffres et équipes. Les trois constats ont été reproduits puis corrigés. Le rendu local à 390 pixels a été contrôlé sans débordement horizontal, avec 23 duels et le filtre du banc ; la traduction anglaise conserve cette largeur. Les boutons d’action mesurent au moins 44 pixels.

Des lectures Classic réelles ont validé les parcours seniors et juniors, en conservant les refus adverses. Les accès U20/NT sont couverts par les tests de contrat et de contexte ; aucune sélection réelle n’a été utilisée pour cette livraison. Les rapports et captures de compte restent privés.

Une première passe de tests avait été lancée pendant la reconstruction Vite : trois initialisations ont échoué sur le répertoire d’assets momentanément absent. La validation finale ci-dessus a été exécutée sur un build stabilisé. Les avertissements existants de dépréciation TestClient et de taille du bundle restent présents.

## Publication

Version publiée le 2 novembre 2026 depuis le commit `24152eb9d6af3a127f371cb7ff9158db4de216bd`, archive SHA-256 `31e328507669f3090dcf042442f3003511a9c242bc74e05fb8bf203b0b1469f0`. Les 30 fichiers statiques servis correspondent octet pour octet à l’archive vérifiée. Santé et version 2.13.0, redirection HTTPS, en-têtes de sécurité et CAPTCHA actif ont été contrôlés ; les 50 accès privés testés sans session renvoient 401 et une connexion sans CAPTCHA renvoie 403.

Les sauvegardes avant et après publication ont réussi. Les contrôles SQLite en lecture seule confirment intégrité, schéma et volumes observés inchangés. L’ancienne version reste disponible pour retour arrière. La configuration existante du service n’a pas été modifiée et aucun nouveau pilote d’écriture Classic n’a été activé.

Le parcours connecté a ensuite été contrôlé sur le site publié : calendrier et comparaison seniors sur ordinateur, changement vers les juniors, calendrier de secours et comparaison à 390 pixels, ouverture de l’aide propre à cet écran puis fermeture sans perdre le rapport. Le rendu mobile observé ne déborde pas horizontalement. Ces contrôles ont utilisé la session du propriétaire, sans nouvelle résolution de CAPTCHA.
