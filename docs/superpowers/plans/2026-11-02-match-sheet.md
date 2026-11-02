# Match sheet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Comparer les deux feuilles Classic et leurs indicateurs depuis une vue mobile dédiée.

**Architecture:** Module Python de lectures bornées, endpoint authentifié par espace, composant React isolé par équipe/population. Réutiliser l’adaptateur Classic et les identités existantes ; aucun ordre Classic.

**Tech Stack:** Python/FastAPI, React/TypeScript, CSS existant, pytest et tests Node.

**Spec:** docs/superpowers/specs/2026-11-02-match-sheet-design.md

## Global Constraints

- Aucun secret ou fait de compte dans Git ; le script original reste privé et n’est jamais exécuté.
- Aucun appel d’écriture Classic ; identités seniors/juniors/U20/NT distinctes.
- Donnée manquante différente de zéro, postes non décalés, fraîcheur explicite.
- Repères d’horaires distincts des échéances confirmées ; quatre langues.
- GitHub et VPS à jour avec sauvegarde et retour arrière disponible.

## Review Focus

- Composition adverse non publiée et réponse partielle : ne pas afficher un Default comme une feuille réelle.
- Un même ID de rencontre dans plusieurs populations : tous les appels et résultats doivent rester dans le contexte choisi.
- Énergie de formats mélangés ou ≤11 : pas de multiplication implicite d’un pourcentage par dix.
- Changement d’espace/équipe pendant une lecture lente : pas de réponse tardive attribuée au mauvais manager.
- Réponses amont incohérentes, identifiants manquants ou erreurs contenant des URLs : refus ou absence explicite sans fuite ni décalage de ligne.

### Task 1: Backend de comparaison et route privée

**Files:** créer server/match_sheet.py, tests/test_match_sheet.py ; modifier server/main.py ; tests de route dans tests/test_match_sheet_routes.py.

**Interfaces:** `SheetCalendarRequest(team_id, match_type)` ; `SheetRequest(team_id, match_type, reference, home_energy_scale='auto', guest_energy_scale='auto')` ; `list_sheet_fixtures(client, team_id, match_type, *, now=None)` ; `fetch_match_sheet(client, request, *, now=None)` ; `build_side` et calculs internes purs. Routes POST `/api/match-sheet/fixtures` et `/api/match-sheet/read`, require_team + auth/CSRF + limite90s.

- [ ] Écrire puis exécuter les tests RED : appartenance au match, appels f/t/lu/p exacts et bornés, 23 places gardées quand une fiche manque, feuille absente, types0/1/2/3, champs invalides, aucune méthode d’écriture. Valeurs de référence : pack huit poids100=800 ; CSR10000/forme7/XP7/énergie100%=10000 ; énergie10 en auto=indice inconnu ; niveau10 explicite=10000.
- [ ] Implémenter les lectures, validations, synthèses et échéances conformément à la spec ; ne retourner qu’une liste blanche de champs.
- [ ] Vérifier tests verts et suites existantes de lecture/authentification. Ajouter tests de routes401/403/404, CSRF et sélection d’un autre espace.
- [ ] Commit backend.

### Task 2: Interface Jour de match

**Files:** créer web/src/match-sheet.tsx, match-sheet-model.ts, match-sheet.css ; modifier navigation.ts, sidebar.tsx, App.tsx, tutorial.tsx et catalogues ; tests web/tests/match-sheet-model.test.ts et match-sheet-render.test.mjs.

**Interfaces:** consomme le JSON de Task1 ; exports `MatchSheet({d,busy})`, validation de contexte et helpers de présentation purs. Ne pas modifier la préparation historique existante.

- [ ] Écrire/exécuter RED : route visible pour clubs et sélections, 23 paires stables, inconnues et couverture, rapport d’une autre équipe/population rejeté, cartes mobile et rôles lisibles.
- [ ] Implémenter formulaire calendrier/ID, deux sélecteurs d’échelle, lecture manuelle, cartes et synthèses ; conserver rapport daté en cas d’erreur, ignorer réponse après démontage/changement de contexte.
- [ ] Intégrer l’accès « Jour de match » dans Préparer le match, aide et quatre langues. Expliquer l’indice et les deux échelles sans présenter un pronostic.
- [ ] Vérifier Node, TypeScript/build, i18n ; commit interface.

### Task 3: Publication vérifiée

**Files:** README.md, docs de validation de version ; version backend et sidebar2.13.0 ; preuves et opérations privées hors Git.

- [ ] Tests Python et Node complets, build, audit des nouveaux fichiers publics ; revue indépendante de toute la branche avec la spec, ce plan et ses cinq points de vigilance.
- [ ] Corriger les constats importants par RED→GREEN, puis sauvegarde prépublication, archive du code commis et build, déploiement atomique sur VPS ; garder le worker Classic désactivé.
- [ ] Vérifier santé/version, assets, accès401, CSRF, CAPTCHA inchangé, intégrité SQLite et parcours authentifié desktop/mobile ; sauvegarde après publication. Ne pas présenter des données de démonstration comme un essai réel.
- [ ] Publier le code sur GitHub, consigner limites et résultat de chaque contrôle, puis informer Pierig et répondre amicalement à Franck dans le fil existant avec les fonctionnalités réellement vérifiées.

## Self-review

Les trois tâches couvrent la spec. Les contrats JSON seront consignés avec les tests de Task1 avant l’interface. Aucun besoin d’accéder au compte de jeu de l’auteur du script ni de réutiliser ses clés. L’import existant du classeur reste pris en charge ; aucun nouveau fichier tableur demandé.
