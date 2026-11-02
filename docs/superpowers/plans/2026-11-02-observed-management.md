# Observed management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rendre les observations seniors/juniors et les quatre derniers matchs directement exploitables sans conclusions inventées.

**Architecture:** Tableau d’effectif extrait dans un composant dédié ; nouveau lecteur de comparaison récente adossé aux contrats Classic existants ; composants React scindés par contexte. Réutilisation des notes et performances privées existantes.

**Tech Stack:** Python/FastAPI/Pydantic/SQLite existants, React/TypeScript/Vite, pytest et node:test.

**Spec:** docs/superpowers/specs/2026-11-02-observed-management-design.md

## Global Constraints

- Aucun changement de droits, nouvelle dépendance ou écriture Classic.
- Données privées, captures et preuves hors Git ; tests synthétiques.
- Inconnues distinctes de zéro, date/source explicites et calculs personnels identifiés.
- Conserver le worktree existant et les préparations sportives.

## Review Focus

- Changement de session/équipe/cohorte pendant une requête : aucune ancienne réponse affichée.
- Résultat0–0 ou champ absent : ne pas confondre score nul et donnée manquante.
- Historique partagé par deux clubs et identifiant partagé senior/junior : déduplication seulement dans le même contexte.
- Étoiles600, données masquées et commentaires longs : pas de plafonnement ni perte de tri/accessibilité.
- Reporter vide ou contradictoire : quatre dernières rencontres conservées, données incohérentes explicitement refusées.

### Task 1: Effectifs observés

Files : web/src/roster-table.tsx, roster-table-model.ts, roster-table.css ; web/src/pages.tsx ; tests Node dédiés, tests/test_academy_statistics.py.

- [ ] Tests RED : tri numérique600/1000/inconnus, colonnes complètes seniors/juniors, notes longues échappées et action fiche, valeurs0 préservées.
- [ ] Implémenter les composants et relier Players, sans nouveau stockage ni changement d’import.
- [ ] Tests GREEN et contrôle du contrat d’import600étoiles ; lien vers performances existantes.

### Task 2: Comparaison des quatre derniers matchs

Files : server/match_recent.py, server/main.py ; tests/test_match_recent.py, tests/test_match_sheet_routes.py ; web/src/match-recent.tsx, match-recent-model.ts, match-recent.css ; web/src/match-sheet.tsx ; tests Node dédiés.

- [ ] Tests RED : dernier4par côté, ordre chronologique fiable,0–0, champs manquants, déduplication, drapeaux4contextes et identité incohérente, erreurs assainies.
- [ ] Lecteur borné : f cible, f last20par participant, noms t, rs sur les4 derniers ; aucune ancienne rencontre de substitution pour masquer un rapport manquant.
- [ ] Route privée/CSRF et contexte ; UI à lecture volontaire, réponse tardive ignorée, rapport précédent conservé sur échec, sources et date.
- [ ] Tests GREEN ; comparaison réelle en lecture seule sur club propre et preuves privées.

### Task 3: Lisibilité, validation et publication

Files : web/src/data-basis.tsx, App.tsx ; quatre catalogues ; tutoriel ; README et bilan de version2.14.0 ; versions backend/sidebar.

- [ ] Tests RED des repères observé/modèle et du parcours des nouvelles vues ; ajouter clés explicites quatre langues.
- [ ] Intégrer repères et aide, sans nouvelles promesses statistiques.
- [ ] Tests ciblés, build puis suites complètes (ne pas construire dist pendant les tests).
- [ ] Revue indépendante de la branche ; corriger tout constat important et vérifier.
- [ ] Commit/GitHub, archive exacte, sauvegardes et déploiement VPS, contrôles publics/SQLite et parcours connecté, preuve privée.
- [ ] Répondre dans le fil du retour après vérification, décrire les apports réels et limites sans prétendre avoir audité toute règle du jeu.
