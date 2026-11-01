# Validation de BRT 2.12.0

Cette version complète les parcours juniors et sélections U20, et corrige les écarts confirmés pendant une revue des calculs. Les préparations BRT restent distinctes des actions effectuées dans Classic.

## Changements

- Matchs juniors dans l’import de fichier, l’import direct avec aperçu, l’historique, les filtres statistiques, la relecture et les dossiers adversaires. Le même numéro peut être conservé séparément en senior, junior, U20 et NT.
- Le type junior `3` est interne à BRT. Les lectures Classic utilisent `youth=1` pour les rencontres, commentaires et scores ; les noms des équipes restent ceux des clubs. Les contextes contradictoires sont refusés.
- Historique individuel filtré par population avant de retenir les 100 observations du joueur. Les fiches juniors ouvrent le bon écran Classic. Les sélections conservent leurs espaces distincts et leurs observations datées.
- Progression collective calculée avant l’arrondi final ; éléments de match incomplets visibles dans le filtre de relecture ; montants du registre affichés sans perte de centimes ; nom groupé tiré de l’opération la plus récente ; données de stade absentes ou invalides laissées inconnues.

## Portée et limites

Les tests des formules vérifient les calculs sur les données fournies, pas la vérité de toutes les données du jeu. Les coefficients de postes, les recommandations tactiques, les projections d’entraînement et les scénarios financiers sont des modèles explicites, pas des formules officielles ni des promesses de victoire ou de revenu.

Les minutes automatiques des juniors/U20/NT restent inconnues tant que le format correspondant de statistiques individuelles Classic n’est pas confirmé. Une compétence révélée n’est pas assimilée à un gain. Un commentaire expiré ou un match de bots ne devient pas un rapport de performance vide réputé complet.

Le calendrier de sélection reste manuel ; la formation, le staff et les finances de ses joueurs restent gérés dans les clubs. Cette version n’ajoute aucun pilote d’écriture dans Classic.

## Vérifications du 1er novembre 2026

- **1 228 tests Python et 203 tests Node réussis**, sans échec ni test ignoré.
- TypeScript et build de production réussis ; **3 645 clés** présentes dans chaque catalogue FR/EN/ES/IT, sans clé manquante ni invalide.
- Revue indépendante des imports, des historiques et des calculs corrigés. Oracles distincts pour les contextes Classic, les collisions entre populations, les montants et les agrégats.
- Parcours Chrome local avec données synthétiques : fiche junior aux compétences inconnues, lien vers le bon écran Classic, quatre rapports partageant un numéro sans mélange, filtre et analyse juniors, espace et contexte d’import U20.
- Contrôle des sources destinées au dépôt public : aucun des secrets connus du projet ni répertoire de données privées détecté.

Le code Python est resté inchangé pendant sa suite. Une correction de texte dans l’en-tête U20 a été intégrée avant l’exécution de tous les tests frontend et du build ; les empreintes finales correspondent aux sources testées. Le contrôle visuel de ce lot porte sur le bureau, pas sur une nouvelle campagne mobile complète.

Deux avertissements restent non bloquants : dépréciation de l’adaptateur HTTP du client de test Starlette et taille du bundle JavaScript principal. Ce dernier mérite encore du découpage pour réduire le téléchargement initial.

## Publication vérifiée

La version 2.12.0 a été déployée le 1er novembre 2026 depuis le commit `cf77386`, après sauvegarde, puis vérifiée sur [brt.bordebat.fr](https://brt.bordebat.fr). Les 30 fichiers statiques servis correspondent exactement aux empreintes du build testé. Les 48 requêtes de contrôle des routes privées sont refusées sans session ; la connexion sans CAPTCHA est refusée, et les protections HTTPS restent présentes.

Le service et le minuteur de sauvegarde sont actifs. Les contrôles SQLite en lecture seule réussissent avant et après publication ; les compteurs observés des tables contrôlées sont inchangés. Une sauvegarde supplémentaire a réussi après la bascule. Aucune migration destructive ni écriture dans Classic n’est incluse.
