# Complete manager implementation plan

> Exécution avec superpowers:subagent-driven-development ; tâches isolées en parallèle selon le mandat de délégation, intégration centralisée.

**Goal:** livrer les sept capacités de l'atelier 2.11.
**Architecture:** trois modules privés autonomes, calculs purs testables, intégration dans navigation/export/aide par le coordinateur.
**Tech Stack:** Python/FastAPI/SQLite, React/TypeScript.
**Spec:** `docs/superpowers/specs/2026-11-01-complete-manager-design.md`.

## Global Constraints

Aucune écriture Classic ni changement du worker ; espaces privés et cohortes séparés ; inconnues distinctes de zéro ; hypothèses et sources visibles ; anciens calculs inchangés ; révisions transactionnelles ; protection des brouillons ; FR/EN/ES/IT ; aucune donnée réelle dans Git. Aucun sous-agent ne committe ni ne déploie.

## Review Focus

Sources modifiées entre aperçu et confirmation ; scores incomplets et échelles incompatibles ; sortie d'un titulaire responsable et couverture du banc ; mélange charges/semaine et charges/match ; transfert corrigé, annulé ou importé deux fois. Chaque tâche vérifie les cas de son domaine.

### Task 1: Staff & tactique

Créer `server/coach_lab.py`, `server/coach_engine.py`, `web/src/coach-lab.tsx`, `web/src/coach-lab.css`, tests dédiés et `docs/coach-lab-methodology.md`. Signature `register_coach_lab(app,store,auth,require_team,state)`, composant `CoachLab(Actions)`, API `/api/coach-lab`. Documents durables `coach_lab:*`, feuilles juniors `coach_lineup:*`, aperçus `coach_preview:*` exclus des exports. Lire l'effectif via state et la bibliothèque `player_performance:observations`. Coefficients, XV, responsables et tactiques décrits par la spec ; interfaces internes conçues dans ce module. Feuille locale seniors compatible avec `lineup:<team>` et junior séparée.

- [x] Tests rouges des calculs et de l'isolation/concurrence, puis implémentation minimale.
- [x] Interface utilisable de bout en bout, traductions fournies hors catalogues partagés.
- [x] Tests verts et revue indépendante, corrections vérifiées.

### Task 2: Économie du stade

Créer `server/stadium_economy.py`, `web/src/stadium-economy.tsx/css`, tests dédiés et `docs/stadium-economy-methodology.md`. Signature `register_stadium_economy(app,store,auth,require_team)`, composant `StadiumEconomy(Actions)`, API `/api/stadium-economy`, KV durable `stadium_economy:*`. Le coordinateur l'intègre dans Stade & finances. Clubs seulement.

- [x] Tests rouges de recettes/net/récupération, inconnues et révisions, puis implémentation.
- [x] Saisie, comparaison actuel/projet, sauvegarde/duplication/export et interface traduite.
- [x] Tests verts et revue indépendante, corrections vérifiées.

### Task 3: Registre des transferts

Créer `server/transfer_ledger.py`, `web/src/transfer-ledger.tsx/css`, tests dédiés et `docs/transfer-ledger-methodology.md`. Signature `register_transfer_ledger(app,store,auth,require_team)`, composant `TransferLedger(Actions)`, API `/api/transfer-ledger`, KV durable `transfer_ledger:*`, aperçus `transfer_preview:*` exclus. Le coordinateur l'intègre dans Mercato & budget. Clubs seulement.

- [x] Tests rouges de balances/frais, doublons, corrections/annulations et imports atomiques, puis implémentation.
- [x] Saisie et import avec aperçu, statistiques, recherche et export réimportable ; traductions.
- [x] Tests verts et revue indépendante, corrections vérifiées.

### Task 4: Intégration et publication

Modifier main.py, exports.py, App/navigation/sidebar/pages/rugby/tutorial, traductions, README et version2.11.0. Liens depuis performances/académie vers le staff ; intégration des modules économiques dans leurs rubriques.

- [x] Tests de routes/auth/export et navigation.
- [x] Revues, tests complets, contrôle synthétique Chrome sur bureau, build et audit public. Voir les limites de vérification dans `docs/release-2.11.0-validation.md`.
- [ ] Commit/publication GitHub, sauvegardes et VPS, contrôles de production, bilan de validation.
