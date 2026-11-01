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

La version 2.11.0, issue du commit `0e1a755`, a été déployée le 1 novembre 2026 à 11 h 29 (Europe/Paris), après une première tentative interrompue par des connexions SSH instables. Le transfert complet et son empreinte ont été vérifiés avant activation.

- Sauvegardes avant et après publication réussies ; service BRT actif, sans redémarrage en boucle.
- Intégrité des bases vérifiée ; nombres de lignes conservés pendant le contrôle de schéma.
- Domaine public : version 2.11.0, redirection HTTPS et en-têtes de sécurité vérifiés.
- Les 30 fichiers publiés correspondent exactement au build local validé.
- Les 40 accès API privés contrôlés répondent 401 sans session. Le CAPTCHA est actif ; une connexion sans jeton CAPTCHA est rejetée (403).
- Aucune erreur applicative relevée dans les journaux des cinq minutes contrôlées après activation.

La limite de contrôle visuel mobile mentionnée plus haut reste applicable ; les contrôles de production ci-dessus ne la remplacent pas.
