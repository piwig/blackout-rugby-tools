# Plan — atelier du manager 2.10

**Goal:** livrer les trois capacités de la feuille de route dans BRT.
**Architecture:** modules FastAPI privés et composants React ; intégration centrale par le coordinateur.
**Tech stack:** Python, SQLite, FastAPI, TypeScript, React.
**Spec:** `docs/superpowers/specs/2026-11-01-manager-workbench-design.md`.
**Global constraints:** aucune donnée réelle dans Git, aucune écriture Classic, isolation des managers, identités club/U20/NT séparées, inconnues et provenance explicites, confirmation atomique et contrôle des révisions.
**Review focus:** confidentialité, permissions des sélections, exactitude statistique, conservation historique et actions réelles de l'interface.

## Tâches

- [x] 1. Vivier : `server/player_pool.py`, `web/src/player-pool.tsx` et styles/tests dédiés. Contrat `register_player_pool(app, store, auth, require_team)`, composant `PlayerPool(Actions)`. API privée `/api/player-pool`. Notes et suivi avec révision ; sources séparées et filtres. Tester doublons inter-contextes, valeurs contradictoires, isolation et concurrence.
- [x] 2. Performances : `server/player_performance.py`, `web/src/player-performance.tsx` et styles/tests dédiés. Contrat `register_player_performance(app, store, auth, require_team, match_credentials, throttle)`, composant `PlayerPerformance(Actions)`. API privée `/api/player-performance`, lecture Classic bornée d’une rencontre via `server/performance_classic.py`, ressource `rs` JSON documentée. Import documenté CSV/JSON avec aperçu puis confirmation, statistiques prudentes par poste, export et correction/suppression. Tester moyennes manuelles, données manquantes, identité des matchs, échelles incompatibles, révisions et séparation des managers.
- [x] 3. Import : `server/import_preview.py`, `web/src/import-preview.tsx`, tests dédiés. Contrat `register_import_preview(app, store, auth, require_team, credentials, throttle)`, composant `ImportPreview(Actions)`. Routes `/api/import/preview` et `/api/import/confirm`. Réutiliser le parseur existant sans modifier son comportement historique ; destinations explicites, aperçu périssable privé, mandat revalidé pour sélection, transaction unique. Tester collision et échec multi-destinations sans écritures partielles.
- [x] 4. Intégration : routes dans `server/main.py`, export des documents privés, navigation, réglages et tutoriel, traductions FR/EN/ES/IT, version 2.10.0. Tests de parcours et construction TypeScript.
- [x] 5. Revue des trois modules et de l'intégration, résolution des défauts, contrôle visuel avec données fictives, tests complets et audit du contenu public.
- [x] 6. Commit et synchronisation du dépôt public, sauvegarde et déploiement du code vérifié sur le VPS, contrôle HTTPS/API/assets et note de validation. Voir `docs/release-2.10.0-validation.md`.

Les trois modules possèdent des fichiers distincts ; les fichiers partagés sont réservés au coordinateur. Les sous-agents ne commitent ni ne déploient. Le choix d'exécution autonome et de publication est déjà autorisé par l'utilisateur.
