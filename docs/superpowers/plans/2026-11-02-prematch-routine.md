# Pre-match routine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Choisir un banc cohérent et préparer les décisions avant les vraies échéances.
**Architecture:** Un helper pur de couverture partagé par les deux moteurs ; lecture de fenêtre et checklist sans appel réseau dans Jour de match ; guide privé et mise à jour de l’automatisation existante via l’outil officiel.
**Tech Stack:** Python, React/TypeScript, pytest/Node, automatisation locale existante.
**Spec:** docs/superpowers/specs/2026-11-02-prematch-routine-design.md

## Constraints and review focus

- Aucun fait de compte ou secret dans Git. Aucun nouveau pilote d’écriture Classic.
- Exactitude seulement selon couverture/score déclarés ; pas de pronostic. Les huit remplaçants ne couvrent pas simultanément toutes les positions par magie.
- Scores historiques et compétences manquantes restent inconnus. Les titulaires imposés sont préservés.
- L’échéance de notre équipe doit venir de Classic avec fuseau ; aucun droit affirmé depuis un horaire indicatif.
- Horaires11h/16h ciblés, même automatisation ; préserver notifications, statut et chat, vérifier le fichier enregistré après l’outil.

### Task 1: Banc partagé et tests de calcul

Files: créer server/bench_selection.py et tests/test_bench_selection.py ; modifier server/optimization.py,server/coach_engine.py et leurs tests.
Interfaces: select_bench(candidates,roles,limit=8), candidats id/covers/score, retourne identifiants stables ; coverage validée contre deux piliers et une option par autre rôle.

- [x] RED : contre-exemple glouton, comparaison exhaustive de petits cas, permutation, inconnues, limites.
- [x] Implémenter la programmation dynamique bornée et intégrer aux deux moteurs sans modifier le XV.
- [x] Vérifier les suites de calcul et de contrats, commit.

### Task 2: Fenêtres et contrôle avant match

Files: web/src/match-sheet-model.ts,match-sheet.tsx, quatre catalogues, tests existants ; versions backend/sidebar2.13.1.
Interfaces: preparationWindow(report) fondée sur retrieved_at et échéances de notre côté ; sheetReadiness(report) avec counts/roles.

- [x] RED : domicile/extérieur, juniors/U20/NT, délais absents/contradictoires/ambigus, responsables manquants.
- [x] Afficher les étapes à la lecture et les contrôles sans changer le jeu ni annoncer une sauvegarde ; adapter le libellé de couverture du banc, aide et quatre langues.
- [x] Node/i18n/build, commit.

### Task 3: Routine, revue et livraison

Files privés: C:/brt/review/piwig-preparation-avant-match.md, point courant et dossier de preuves ; automatisation existante. Documentation de validation publique sans données de compte.

- [x] Guide pré-match et calendrier11h/16h via automation_update, sauvegarde et relecture exacte de la configuration.
- [x] Revue indépendante de la branche, corrections RED/GREEN utiles, suites complètes et build stabilisé, contrôle de confidentialité.
- [x] Publier GitHub/VPS avec sauvegardes et retour arrière ; contrôles publics/authentifiés et journal privé. Répondre à Franck après publication vérifiée.
