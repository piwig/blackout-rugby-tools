# Fiabiliser les clubs affiliés et les sélections

Le retour utilisateur demande une comparaison de BRM V4 et une meilleure prise en charge des affiliés, U20 et NT. BRT possède déjà ces contextes ; ce lot corrige les parcours défaillants reproduits avant d'étendre les outils de sélection.

## Résultat attendu

- Un ODS générique importe joueurs, métadonnées et planning dans le club explicitement choisi. Les feuilles historiques nommées Moeskroen/LaTouff restent une compatibilité documentée, sans imposer leur destination à une feuille générique.
- Une réponse Classic explicitement vide remplace l'ancien effectif par un effectif vide lors d'une synchronisation ciblée. Une réponse malformée ne détruit rien.
- Une lecture réussie de joueurs inchangés actualise leur fraîcheur, sans fabriquer de progression ni écraser la première observation historique.
- Une sélection suspendue expose son état et la reprise dans Connexion & données, sans bouton de synchronisation voué à l'échec.
- Le calendrier manuel des sélections reste disponible ; l'import Classic non pris en charge n'est plus proposé. L'académie de club n'est plus proposée dans la progression des sélections.
- Le sélecteur distingue clubs du compte, clubs suivis et sélections actives/suspendues. Les priorités de toutes les équipes restent accessibles depuis le tableau de bord sélection.

## Contraintes

Espaces privés par manager, identifiants club/U20/NT distincts, aucune écriture au jeu ni élargissement des droits. FR/EN/ES/IT. Données synthétiques pour les tests. Aucune donnée de compte, preuve de navigation ou clé dans Git. Conserver les brouillons et les contrôles de concurrence existants.

## Limites de ce lot

Le vivier transversal de candidats et les formules fondées sur les performances de match demandent un cadrage distinct. Le format NT réel non observé reste explicitement non validé ; aucune compatibilité ne sera inventée.
