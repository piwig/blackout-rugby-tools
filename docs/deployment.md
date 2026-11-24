# Déployer Blackout Rugby Tools

Ce guide décrit une installation de l’application. Les clés, adresses de notification, données de managers et journaux d’exploitation restent hors de Git.

## Préparer la version

Créer un environnement Python, installer `requirements.txt`, puis exécuter `npm ci` et `npm run build` dans `web/`. Le serveur sert le répertoire `web/dist`. Les services et scripts d’exemple sont dans `deploy/`.

Avant publication, exécuter les tests Python, les tests Node et `node web/scripts/check-i18n.mjs`. `deploy/package_release.py` prépare une archive à partir des sources commises et du build, en excluant les dossiers privés.

À l’extraction, vérifier que le compte du service peut lire les sources et traverser leurs répertoires. Avec `tar --no-same-permissions`, un masque hérité `077` rendrait ces fichiers publics illisibles pour ce compte : utiliser un masque adapté, par exemple `022`, uniquement pour l’installation du code. Conserver des permissions privées distinctes pour données, clés, configurations et archives de sauvegarde.

## Configurer le service

Exécuter avec un compte système dédié et un seul processus Uvicorn :

```sh
uvicorn server.main:app_factory --factory --host 127.0.0.1 --port 3042 --workers 1
```

Le proxy HTTPS relaie les requêtes vers cette adresse locale. Configurer `BRT_DATA_DIR` dans un répertoire durable accessible uniquement au service, `BRT_PUBLIC_URL` avec votre domaine et `BRT_SECURE=1` en production. Le mot de passe initial `BRT_PASSWORD` sert à la création de la première base ; le fournir par un fichier d’environnement protégé, jamais dans le dépôt.

Pour Cloudflare Turnstile, renseigner `BRT_TURNSTILE_ENABLED=1`, la clé publique de site et la clé secrète serveur, avec le domaine de l’installation autorisé chez le fournisseur. Les variables d’inscription et de notification SMTP sont décrites dans le README. Les secrets restent côté serveur.

## Audience facultative avec Umami

La mesure est désactivée par défaut. Pour la raccorder à une installation Umami
existante, fournir dans l'environnement privé du service :

```ini
BRT_AUDIENCE_ENABLED=1
BRT_AUDIENCE_SCRIPT_URL=https://mesure.example/mesure.js
BRT_AUDIENCE_WEBSITE_ID=UUID-DU-SITE-BRT
BRT_AUDIENCE_HOSTNAME=brt.example
```

Le site ID est public ; aucun mot de passe Umami ne doit figurer dans ces valeurs.
Le serveur refuse une URL non HTTPS, avec credentials, query ou fragment, un
hostname invalide ou un UUID invalide : la mesure reste alors désactivée. La CSP
n'autorise l'origine du collecteur que pour les scripts et les connexions. Le
contrat public `GET /api/audience/options` n'expose que les réglages du tracker.

Le frontend désactive la collecte automatique et transmet uniquement des vues de
rubriques à chemins/titres fixes, avec domaine de provenance externe ou vide.
Les identifiants, contenus de clubs, formulaires et URL réelles ne sont pas
transmis. Umami traite techniquement les requêtes/IP/User-Agent pour produire ses
mesures ; les agrégats ne représentent pas des personnes identifiées. Do Not Track,
le choix local de désactivation et les administrateurs connectés excluent la
collecte. Un administrateur avant connexion peut rester compté comme visite publique.
Un bloqueur ou un échec du collecteur ne doit pas bloquer l'application.

Dans Vigie, ajouter le projet avec un préfixe `UMAMI_BRT` distinct et désactiver
son monitoring SEO/IA si seule l'audience est souhaitée. Le lecteur Umami doit être
View only globalement et team-view-only dans une équipe dédiée contenant BRT seul,
possédée par l'administrateur. Ne pas réutiliser ou élargir un lecteur d'un autre
projet. Garder son secret uniquement dans l'environnement privé de Vigie.

Après activation, contrôler les payloads dans le navigateur, la réception dans
Umami puis les agrégats Vigie à 7/30 jours. Séparer la recette du trafic organique.
Les visites antérieures à l'activation ne sont pas reconstituées. Pour désactiver,
retirer `BRT_AUDIENCE_ENABLED=1` puis redémarrer BRT : aucune donnée métier n'est
modifiée.

## Conserver et restaurer les données

Sauvegarder ensemble le registre des comptes, les bases de chaque manager et leurs fichiers `encryption.key`. Sans la clé associée, les identifiants API chiffrés ne sont pas restaurables. Les scripts de sauvegarde fournis réalisent des copies cohérentes des bases SQLite. Protéger aussi les archives et toute copie distante.

`deploy/backup.py` ouvre les sources en lecture seule, y compris leurs données WAL validées. Chaque base a une photographie cohérente ; les bases sont copiées successivement. Le registre, le schéma courant, chaque espace qu’il référence et les clés sont obligatoires. L’archive complète est publiée seulement après les contrôles ; une erreur ne remplace pas une sauvegarde précédente. La rétention locale conserve **30 archives**, donc 30 exécutions réussies, et non 30 jours. Le service envoie ensuite les sauvegardes, les archives de code et `/etc/brt` vers Restic. Un succès du service ne remplace pas un exercice de restauration.

`deploy/verify_backup.py` restaure par défaut le dernier snapshot Restic marqué `brt` dans un répertoire temporaire puis contrôle l’inventaire, l’intégrité et le schéma SQLite, le format des clés, une archive de code comprenant le frontend construit et les fichiers `contact.env` et `security.env` non vides. La limite de fraîcheur est de 36 heures ; `--max-age-hours` permet de choisir explicitement une autre limite pour examiner un historique. Les archives au format de nom précédent restent lisibles.

Pour contrôler une copie déjà restaurée en isolement, sans réseau :

```sh
python3 deploy/verify_backup.py --restored-root /var/tmp/brt-exercice-isole
```

Le mode `--archive /chemin/brt-....tar.gz` contrôle uniquement les données d’une archive locale ; il ne vérifie pas le code ni la configuration serveur. Ces commandes n’importent pas l’application, ne lancent aucun worker et ne déchiffrent aucun identifiant API. Elles ne prouvent donc pas que les clés restaurées correspondent aux valeurs chiffrées, que les secrets serveur sont encore valides ou que l’ensemble de l’application redémarrera correctement. Garder leurs résultats agrégés dans les preuves privées.

Arrêter le service avant une restauration ou une migration de format. Conserver la version précédente du code et une sauvegarde compatible pour permettre un retour arrière. Les journaux, adresses de destinataires et références de comptes personnels doivent rester dans les documents d’exploitation privés.

La perte possible correspond aux écritures postérieures au dernier point de sauvegarde disponible. Un commentaire de match disparu de Classic ne peut pas être récupéré par une nouvelle lecture s’il manque aussi à cette sauvegarde. Après une restauration réelle, maintenir `BRT_VACATION_WORKER=0` jusqu’à la revue des règles et des actions Classic depuis ce point : restaurer SQLite ne remet pas le jeu externe dans son état passé.

## Vérifier une publication

Après démarrage, contrôler `/api/health`, la redirection HTTPS, les en-têtes de sécurité, les fichiers statiques et les journaux du service. Sans session, les API métier et le formulaire de contact doivent répondre 401. Vérifier la connexion, l’inscription et le CAPTCHA sur le domaine réel, puis la séparation des espaces de managers.

Le code public n’accorde aucun accès aux données de l’instance hébergée. Les actions vers Classic conservent leurs contrôles et nécessitent les autorisations propres au compte.
