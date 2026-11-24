# Validation BRT 2.16.0 — audience facultative

Le raccordement ajoute des vues de rubriques à l'installation Umami/Vigie
existante. La mesure est désactivée tant que l'administrateur n'a pas fourni les
réglages du site. Aucun abonnement ou paquet supplémentaire n'est nécessaire.

## Contrat vérifié localement

- Payload manuel limité à cinq champs : site, hostname fixe, chemin synthétique,
  titre générique et provenance externe réduite au domaine.
- Ni identifiant utilisateur/club/joueur, ni contenu importé, texte saisi,
  URL réelle, query ou fragment. Collecte automatique désactivée.
- Do Not Track, refus local, stockage inaccessible ou saturé, administrateur
  connecté et hostname différent empêchent la collecte.
- Les réponses tardives revérifient l'écran et les exclusions ; les vues
  consécutives sont dédupliquées, A → B → A compte trois consultations.
- Les écrans de démarrage/erreur et les notices remplaçant une rubrique
  indisponible ne sont pas des consultations de rubrique.
- Options publiques en lecture seule et réglages malformés refusés sans élargir
  la CSP. L'origine de la CSP provient de composants ASCII validés.
- Information et choix de désactivation disponibles dans les quatre langues.

## Résultats du 24 novembre 2026

- Python : **1 499 tests réussis**.
- Node : **276 tests réussis**, dont 24 tests audience/intégration/interface.
- Catalogues : **3 888 clés** par langue, sans clé manquante ou invalide.
- TypeScript et build Vite réussis ; avertissement existant de taille du bundle.
- Revue indépendante effectuée. Les défauts de configuration Unicode, de refus
  non persistant, de provenance interne et de rubrique indisponible sont couverts
  par des régressions observées rouges puis vertes.

Une première suite exécutée pendant la reconstruction du frontend avait rencontré
deux indisponibilités transitoires du dossier de build et le contrat de routes
publiques à compléter. La suite finale a été exécutée après stabilisation du build
et adaptation explicite de l'unique nouvelle route publique. Les autres API
métier restent privées.

La vérification de publication et de réception réelle reste à consigner après
déploiement. Les preuves opérationnelles, secrets et mesures de l'instance
hébergée restent hors de Git.

## Interprétation

Les mesures ne reconstituent pas les visites passées. Un visiteur technique ne
représente ni une personne identifiée ni un compte actif ; bloqueurs et refus
réduisent la couverture. Les visites de recette doivent être distinguées des
visites organiques. Un administrateur avant connexion peut être compté comme
visite publique. Le connecteur MCP et la réception dans le dashboard doivent
être vérifiés séparément.
