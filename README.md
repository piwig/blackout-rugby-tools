# Blackout Rugby Tools

Application privée pour Blackout Rugby **Classic**, réalisée à partir du mail de Franck du 30 octobre 2026 et de ses six pièces jointes.

## Utiliser

Interface en français : tableau de bord, académie et suivi des jeunes, compétences et comparaisons, composition du XV, historique, plans d'entraînement 16 semaines × 4 créneaux, calculateur de stade, analyses par zone, import ODS/CSV/JSON et exports.

Les données importées de `Moeskroen.ods` concernent Moeskroen (72450) et LaTouff (72444). Le classeur est daté du 27 octobre 2026. Les autres clubs des scripts sont préconfigurés sans données fictives.

La connexion à l'outil est distincte du jeu. Les clés développeur Classic et les clés manager de chaque club se renseignent dans **Connexion & données**. Les champs vides conservent les valeurs existantes. Elles sont chiffrées en base et ne sont jamais renvoyées par l'API. Le mot de passe du jeu n'est jamais demandé par l'outil.

## Calculs et limites

- Projection WC : règle personnelle de `ctr_ya.sql`, pas une règle générale d'éligibilité officielle.
- Les compétences inconnues ne sont ni estimées ni converties en zéro.
- Affinités par poste : moyennes pondérées explicables, pas une simulation du moteur.
- Stade : ratios 22/39/30/8/1 % du classeur ; multiplicateur modifiable, sans prévision de rentabilité.
- Matchs : clés `(type,id)`, 0 club / 1 U20 / 2 NT. Les zones sont relatives à chaque équipe. Les commentaires API sont classés uniquement lorsqu'une règle textuelle explicite correspond ; ces résultats sont **estimés** et leur couverture est affichée. L'import d'événements déjà classés utilise les champs `field`, `possession`, `att`.
- Les fonctions PostgreSQL de reclassement, le parseur PHP et les requêtes d'entraînement appelés par les scripts n'étaient pas joints. Une équivalence exacte avec tous les anciens résultats de Franck ne peut donc pas être certifiée.
- Les plannings et le XV sont sauvegardés dans l'outil ; aucun entraînement, transfert ou tactique n'est modifié dans le jeu.

## Développement

Python 3.12+, Node 22.12+.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:BRT_PASSWORD='<mot de passe initial fort>'
$env:BRT_SECURE='0'
.\.venv\Scripts\python.exe -m uvicorn server.main:app_factory --factory --host 127.0.0.1 --port 3042
```

Le mot de passe initial n'est requis que pour créer la base. Ne pas le commettre. Construire l'interface avec `npm ci` et `npm run build` dans `web/`. Le serveur sert `web/dist`.

Tests : `.\.venv\Scripts\python.exe -m pytest -q`. Les tests utilisent des bases temporaires et n'appellent pas le jeu.

## Exploitation VPS

- `/opt/brt/releases/<date>` : versions déployées ; `/opt/brt/current` : lien vers la version active.
- `/opt/brt/venv` : environnement Python.
- `/var/lib/brt/brt.sqlite` : base privée ; `/var/lib/brt/encryption.key` : clé indispensable à la restauration des identifiants API.
- `brt.service` : compte système dédié, écoute `127.0.0.1:3042`, limite mémoire 512 Mo.
- nginx + certificat TLS : `brt.bordebat.fr`, proxy Cloudflare.
- `brt-backup.timer` : chaque jour à 02 h 35 Europe/Paris ; 30 archives locales avec base cohérente et clé.

Vérifier : `systemctl status brt`, `journalctl -u brt -n 50`, `curl http://127.0.0.1:3042/api/health`.
Revenir au code précédent : modifier le lien `/opt/brt/current` vers la version conservée puis `systemctl restart brt`. Sauvegarder la base avant toute migration.
Restaurer les données : arrêter le service, extraire une archive contrôlée dans un répertoire temporaire, vérifier `PRAGMA integrity_check`, remplacer la base et la clé dans `/var/lib/brt`, remettre propriétaire `brt:brt` et droits 0600, redémarrer. Ne pas exposer les archives par nginx.

`private-source/`, `data/` et `review/` sont exclus de Git. Les pièces jointes contenant les anciens secrets ne sont pas déployées.
