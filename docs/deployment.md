# Déployer Blackout Rugby Tools

Ce guide décrit une installation de l’application. Les clés, adresses de notification, données de managers et journaux d’exploitation restent hors de Git.

## Préparer la version

Créer un environnement Python, installer `requirements.txt`, puis exécuter `npm ci` et `npm run build` dans `web/`. Le serveur sert le répertoire `web/dist`. Les services et scripts d’exemple sont dans `deploy/`.

Avant publication, exécuter les tests Python, les tests Node et `node web/scripts/check-i18n.mjs`. `deploy/package_release.py` prépare une archive à partir des sources commises et du build, en excluant les dossiers privés.

## Configurer le service

Exécuter avec un compte système dédié et un seul processus Uvicorn :

```sh
uvicorn server.main:app_factory --factory --host 127.0.0.1 --port 3042 --workers 1
```

Le proxy HTTPS relaie les requêtes vers cette adresse locale. Configurer `BRT_DATA_DIR` dans un répertoire durable accessible uniquement au service, `BRT_PUBLIC_URL` avec votre domaine et `BRT_SECURE=1` en production. Le mot de passe initial `BRT_PASSWORD` sert à la création de la première base ; le fournir par un fichier d’environnement protégé, jamais dans le dépôt.

Pour Cloudflare Turnstile, renseigner `BRT_TURNSTILE_ENABLED=1`, la clé publique de site et la clé secrète serveur, avec le domaine de l’installation autorisé chez le fournisseur. Les variables d’inscription et de notification SMTP sont décrites dans le README. Les secrets restent côté serveur.

## Conserver et restaurer les données

Sauvegarder ensemble le registre des comptes, les bases de chaque manager et leurs fichiers `encryption.key`. Sans la clé associée, les identifiants API chiffrés ne sont pas restaurables. Les scripts de sauvegarde fournis réalisent des copies cohérentes des bases SQLite. Protéger aussi les archives et toute copie distante.

Arrêter le service avant une restauration ou une migration de format. Conserver la version précédente du code et une sauvegarde compatible pour permettre un retour arrière. Les journaux, adresses de destinataires et références de comptes personnels doivent rester dans les documents d’exploitation privés.

## Vérifier une publication

Après démarrage, contrôler `/api/health`, la redirection HTTPS, les en-têtes de sécurité, les fichiers statiques et les journaux du service. Sans session, les API métier et le formulaire de contact doivent répondre 401. Vérifier la connexion, l’inscription et le CAPTCHA sur le domaine réel, puis la séparation des espaces de managers.

Le code public n’accorde aucun accès aux données de l’instance hébergée. Les actions vers Classic conservent leurs contrôles et nécessitent les autorisations propres au compte.
