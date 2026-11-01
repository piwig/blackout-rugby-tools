# Validation de BRT 2.11.0

Version consacrée à l'atelier Staff & tactique, à l'économie du stade et au registre des transferts réalisés. Les nouveaux écrans s'intègrent aux rubriques existantes ; les réglages avancés se déplient à la demande.

## Contrôles avant publication — 1 novembre 2026

- Suite Python complète : 1 146 tests réussis ; avertissement préexistant Starlette/httpx.
- Suite d'interface Node : 171 tests réussis.
- TypeScript et build Vite réussis. Le bundle principal dépasse encore le seuil de recommandation de Vite.
- Catalogues français, anglais, espagnol et italien : 3 631 clés par langue, sans clé manquante.
- Revues indépendantes des trois modules puis de leur intégration. Les défauts relevés ont été corrigés et revérifiés.
- Contrôle Chrome sur données synthétiques : préparation et sauvegarde de feuilles seniors et juniors distinctes, relecture après sauvegarde, calcul d'un scénario de stade vérifié à la main, duplication et persistance, création et correction d'un transfert avec balance et historique cohérents.
- La saisie automatisée du champ de date natif n'a pas pu être confirmée dans Chrome. Un contrôle ciblé du composant vérifie la conservation d'une date modifiée et sa conversion Europe/Paris vers UTC. La vérification visuelle mobile reste à compléter, le contrôle du navigateur s'étant arrêté avant cette étape.

## Portée

Les propositions sportives sont des aides explicables fondées sur les données disponibles et les coefficients choisis. Les compétences inconnues ne sont pas inventées. Les feuilles enregistrées restent locales à BRT ; cette version n'ajoute aucune écriture dans Classic.

Les scénarios économiques utilisent les hypothèses déclarées. Le registre couvre des opérations terminées saisies ou importées ; il ne modifie pas la trésorerie du jeu. Les tests et les captures de contrôle n'utilisent aucune donnée de compte réelle dans ce dépôt public.

## État de publication

Le code 2.11.0 est publié sur la branche principale. L'archive de déploiement est préparée, mais son transfert vers le VPS a expiré lors de l'établissement de la connexion SSH. Aucun basculement de version n'a été exécuté. Au dernier contrôle du 1 novembre, le domaine public répond encore en version 2.10.0. Les sauvegardes avant/après publication et les vérifications de production de 2.11.0 restent à effectuer après rétablissement de cet accès.
