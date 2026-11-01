# Validation de BRT 2.10.0

Version publiée le 1er novembre 2026 sur [brt.bordebat.fr](https://brt.bordebat.fr), depuis le commit applicatif `9fd1e81`.

## Capacités livrées

- Vivier privé commun aux clubs, académies et sélections : sources séparées, divergences visibles, filtres cohérents, notes et suivi avec contrôle de concurrence.
- Performances observées par poste : lecture d'une rencontre Classic terminée, import CSV/JSON avec aperçu, correction et export, regroupements par contexte et échelle, données manquantes explicites.
- Aperçu d'import d'effectifs : choix explicite de chaque destination, chronologie protégée, mandat de sélection revalidé et confirmation atomique de tout le lot.
- Navigation, tutoriel et contenus français, anglais, espagnol et italien intégrés.

## Vérifications

La suite complète compte **1 070 tests Python** et **147 tests Node** réussis. TypeScript et la construction Vite de production passent. Les quatre catalogues partagent 3 275 clés, sans clés manquantes ni paramètres incohérents. Les revues indépendantes des modules, de l'intégration et des corrections sont terminées.

Les parcours Chrome ont été contrôlés avec des données fictives : suivi et relecture du vivier, import de plusieurs feuilles vers plusieurs destinations, confirmation et persistance des performances. Pour les notes 6, 8 et inconnue, l'interface affiche une moyenne de 7 sur deux notes connues ; 60 minutes, inconnues et 20 donnent 80 minutes renseignées. Le garde de navigation a déclenché son avertissement ; ses cycles de confirmation et d'abandon sont couverts par les tests. Le contrôle manuel complet de fermeture du dialogue a été limité par l'outil de pilotage Chrome.

Le correctif de largeur a été vérifié à 1 112 px et 390 px : filtres dans le cadre et tableaux défilant dans leur propre conteneur. Les traductions ont également été vérifiées dans le navigateur. Une lecture réelle des ressources Classic a validé l'adaptateur, sans ordre envoyé au jeu ; aucune donnée de compte n'est publiée dans ce dépôt.

## Publication

L'archive issue du commit et de la construction vérifiés a été contrôlée par SHA-256. Sauvegardes avant et après déploiement réussies ; service actif après redémarrage. Le site public retourne la version 2.10.0, et ses 30 fichiers statiques correspondent exactement à la construction locale.

Les contrôles HTTPS, en-têtes de sécurité, CAPTCHA et refus des routes privées sans authentification passent. Toutes les bases présentes passent le contrôle d'intégrité et conservent leurs nombres de lignes lors de la vérification du stockage.

## Limites connues

Les positions du rapport Classic sont des positions de départ, pas une chronologie des postes joués. Les minutes seniors sont des totaux de match ; les minutes juniors, U20 et NT restent inconnues tant que leur format de statistiques n'est pas établi. Les faibles échantillons sont signalés et les échelles incompatibles restent séparées. Voir la [méthodologie](manager-workbench-methodology.md).

La construction conserve l'avertissement de taille du principal fichier JavaScript ; la suite Python signale une dépréciation du client de test Starlette/httpx. Aucun des deux n'a empêché les vérifications ou le déploiement.
