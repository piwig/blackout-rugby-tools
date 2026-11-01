# Atelier du manager — version 2.10

## Objectif

Compléter les parcours multi-clubs et sélections avec trois outils utilisables ensemble : un vivier privé, un comparatif des performances observées par poste et un import de fichiers avec destinations explicites. L'autorisation de réalisation suit la feuille de route `docs/selection-workbench-roadmap.md`.

## Architecture et contraintes

Conserver React/TypeScript, FastAPI et les bases SQLite privées par manager. Ajouter des modules indépendants enregistrés dans `create_app`. Toutes les routes exigent l'authentification et les écritures la protection CSRF existante. Aucun envoi dans Classic, aucune modification du pilote automatique, aucune donnée de compte dans Git. Les identifiants club, `u20:` et `nt:` demeurent distincts.

Les données inconnues restent inconnues. Ne pas déduire des minutes du nombre de titularisations, ni des notes du CSR, ni une éligibilité internationale de l'âge. Les périodes, sources, effectifs et petits échantillons doivent rester visibles. Les enregistrements périmés et contradictoires ne doivent pas devenir artificiellement récents.

## 1. Vivier privé

Une nouvelle rubrique affiche les joueurs observés dans les effectifs seniors, académies et sélections du manager. Regrouper un même identifiant joueur sans fusionner silencieusement ses observations : garder chaque source, équipe, cohorte et date, signaler les valeurs incompatibles. Filtres sur texte, nationalité, âge, poste estimé, disponibilité connue et données partielles. Une liste de suivi et des notes propres au vivier sont conservées avec révision, indépendamment des notes de chaque club. Les sélections en pause restent consultables comme archives, clairement identifiées. Pagination et plafonds explicites.

## 2. Performances par poste

Une rubrique compare observations de match, nombre de rencontres, notes et minutes effectivement renseignées, par poste et fenêtre de temps. Distinguer contexte club/juniors/U20/NT, compétition, adversaire et lieu. Ne pas mêler arbitrairement des échelles de notes différentes. Exposer moyenne, minimum, maximum, effectif de l'échantillon et couverture des minutes, avec un avertissement sur les faibles échantillons. Les compétences actuelles peuvent être montrées à côté, sans composite prétendument optimal.

Une lecture directe des résumés Classic (`rs`) et des minutes de rencontre (`fs`) complète le parcours après vérification du format officiel et d’une réponse réelle. La rencontre doit être terminée et appartenir à l’équipe/contexte demandé. Les minutes totales du joueur ne sont pas attribuées à un poste après changement de position ; les postes de banc restent inconnus. Les anciennes échelles demeurent séparées et des bornes non documentées restent inconnues. Lecture puis aperçu et confirmation privée, sans aucun envoi dans le jeu.

Un import CSV/JSON documenté et vérifié permet de saisir les observations qui ne sont pas fournies par les imports Classic existants. Aperçu, provenance, validation, dédoublonnage et confirmation atomique avant écriture. Aucun appel à une ressource API supposée ; une intégration automatique exige un format primaire établi. Export et suppression/correction des observations privées. L'absence de notes ne doit pas produire des zéros.

## 3. Aperçu d'import d'effectifs

Analyser ODS/CSV/JSON sans écriture, montrer les jeux de données reconnus, leurs joueurs et leur destination. Permettre de choisir explicitement club et cohorte, ou sélection active déjà rattachée. Aucune destination implicite fondée uniquement sur un ancien nom de feuille. Valider toutes les destinations et collisions avant une confirmation atomique. Les données annexes du classeur doivent être annoncées et mappées sans ambiguïté, sinon exclues explicitement de ce parcours. Préserver le parcours historique compatible.

Un aperçu est privé, périssable et inutilisable depuis un autre compte. Revalider la révision des données et les droits à la confirmation. L'import manuel d'une sélection ne crée aucun mandat ; seule une sélection rattachée avec mandat confirmé est admissible. Une perte de mandat, une pause ou un changement de compte invalide la confirmation.

## Expérience et validation

Interface française, anglaise, espagnole et italienne, responsive, accessible et cohérente avec l'univers rugby actuel. Ajouter des explications et le parcours au tutoriel. Tester les frontières de comptes, collisions d'identifiants, import ancien, valeurs manquantes, concurrence, dédoublement et perte de mandat. Vérifier les calculs avec des exemples calculés à la main et les actions par des tests rendus. Contrôle visuel avec données fictives, suite complète, revue indépendante, publication GitHub puis déploiement vérifié.
