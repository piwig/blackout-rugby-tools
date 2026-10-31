# Blackout Rugby Tools

**Application : [brt.bordebat.fr](https://brt.bordebat.fr)** · [Dépôt GitHub](https://github.com/piwig/blackout-rugby-tools)

Le code source est public. **Compte BRT obligatoire pour utiliser l’application.** Créez votre compte, puis connectez-vous pour accéder aux outils et au formulaire Contact & idées. Chaque manager dispose de son espace privé.

Atelier pour Blackout Rugby **Classic**, organisé en espaces privés par manager, réalisé à partir du mail de Franck du 30 octobre 2026 et de ses six pièces jointes.

## Utiliser

Interface en français, anglais, espagnol et italien : tableau de bord, académie et suivi des jeunes, compétences et comparaisons, composition du XV, historique, plans d'entraînement 16 semaines × 4 créneaux, calculateur de stade, analyses par zone, import ODS/CSV/JSON et exports.

Depuis la connexion, **Créer mon compte** ouvre l’inscription publique lorsqu’elle est activée. Le formulaire demande un identifiant unique de 3 à 40 caractères, un mot de passe BRT de 12 à 128 caractères et une adresse e-mail. Un avatar est facultatif : maillot, blason, trophée ou rugby BRT ; le maillot est proposé par défaut. L’adresse est contrôlée syntaxiquement, sans vérification de sa propriété ni réinitialisation automatique du mot de passe par e-mail.

L’inscription connecte le manager à un espace vide, sans droits d’administration. Il peut importer son compte Classic ou ajouter un club manuellement. Chaque manager dispose d’une base et d’un fichier de clé, avec ses clubs, notes, plannings, compositions et matchs séparés. Les nouveaux espaces reçoivent une nouvelle clé ; une migration historique a pu copier la même valeur de clé dans deux fichiers distincts. Les anciens comptes sans e-mail restent utilisables, et l’administrateur peut encore créer un accès. Changer son mot de passe révoque toutes ses sessions.

Dans **Connexion & données**, coller la clé d’accès Classic complète (m=…&mk=…) importe le compte, ses clubs, les seniors et les académies. Le bouton d’actualisation relit toutes les équipes. Une erreur API avant la fin de la collecte conserve les observations précédentes.

La connexion à l'outil est distincte du jeu. Les clés développeur Classic et les clés manager de chaque club se renseignent dans **Connexion & données**. Les champs vides conservent les valeurs existantes. Elles sont chiffrées en base et ne sont jamais renvoyées par l'API. Le mot de passe du jeu n'est jamais demandé par l'outil.

Le sélecteur de langue est disponible dès la connexion et dans l’atelier. Le choix est conservé dans le profil ; les noms, notes et commentaires source restent dans leur langue d’origine.

Dans **Analyse des matchs**, choisissez une rencontre récente ou collez son identifiant/lien officiel Classic, vérifiez l’aperçu puis confirmez l’import direct. La liaison par clé ne se fait qu’une fois dans **Connexion & données** ; aucun mot de passe du jeu n’est demandé. JSON/CSV restent disponibles dans les options avancées (8 Mo, 20 000 événements).

L’atelier de classement permet de corriger attaque, type, côté et zone, de distinguer un événement hors attaque et de rétablir la source. Les corrections sont privées, séparées du commentaire original et protégées contre les modifications concurrentes. Des exemples volontairement mémorisés peuvent suggérer une catégorie pour un commentaire similaire ; aucune suggestion n’est appliquée automatiquement.

L’historique paginé donne accès à tous les matchs enregistrés. Ses statistiques portent sur tous les matchs filtrés : type, saison, nom d’équipe, résultats connus, points, attaques, zones et couverture par saison. Les scores inconnus sont exclus des moyennes. Les corrections des événements identiques survivent à un réimport ; celles qui ne correspondent plus restent signalées. Voir la [méthodologie de relecture et d’import](docs/match-review-methodology.md).

## Tutoriel intégré

Le menu **Tutoriel & aide** présente vingt et un chapitres dans ce lot, dont l’inscription, le contact, le profil, la progression, le suivi quotidien, le calendrier et le laboratoire de composition. Leur nombre et la durée totale sont calculés depuis le catalogue. Le guide comprend une FAQ recherchable, un lexique et les limites des estimations. Le tableau de bord et le premier accueil sans club proposent **Commencer le tutoriel**. Sur chaque écran, **Mode d’emploi** ouvre le chapitre pertinent sans démonter le formulaire en cours ; Échap ferme l’aide et rend le focus au bouton.

Les chapitres peuvent être marqués comme lus. Ces repères sont séparés par identifiant sur le navigateur utilisé, sans modifier les données des clubs. Ils se synchronisent entre le guide et son dialogue.

## Profil et progression

**Mon profil** conserve le nom affiché, les initiales, le numéro de maillot et l’avatar. Le club de cœur est facultatif et distinct des clubs Classic gérés : Toulouse, La Rochelle, Leinster, Racing 92, Toulon, Clermont, Munster ou Crusaders. Leurs huit logos réels sont servis localement ; les sources et la mention d’indépendance sont accessibles dans les crédits. Le profil propose aussi une densité confortable ou compacte, du texte normal ou grand, des mouvements réduits, une page de départ et une bannière stade ou vestiaire. Les six rubriques du tableau de bord peuvent être masquées et réordonnées. Une sauvegarde concurrente conserve le brouillon et demande de comparer les versions.

**Progression** présente séparément les seniors et l’académie, par joueur ou moyenne collective, avec filtres de dates, compétences et CSR. Les courbes et leur tableau reprennent les dates et sources réellement conservées. Une valeur inconnue reste vide ; son apparition est un dévoilement, sans gain calculé. Les contradictions, changements d’effectif, différences de couverture et limites de lecture sont signalés. Aucune évolution n’est interpolée entre les observations, et une variation ne démontre pas l’effet d’un entraînement. Voir la [méthodologie](docs/optimization-methodology.md#progression-observée-et-calculs-doptimisation).

## Contact & idées

Le formulaire est réservé aux managers connectés pour signaler un bug, demander une amélioration ou proposer une nouveauté. Il demande un sujet, un message, un e-mail de réponse et l’accord explicite pour transmettre ces champs à Pierig. Aucun mot de passe ou clé API n’est nécessaire. Son identifiant est associé par la session ; une session expirée refuse l’envoi et demande une nouvelle connexion.

Les messages connectés figurent dans l’historique privé du manager. La boîte administrateur rassemble les envois et permet les statuts **Reçu**, **En cours de lecture**, **Prévu** et **Traité**, avec contrôle des modifications concurrentes. Une notification SMTP peut informer l’administrateur lorsqu’elle est configurée ; son échec ne perd pas le message. Elle contient une référence et un lien vers la boîte, sans reprendre le texte du message. Les réponses aux managers ne sont pas envoyées automatiquement.

L’export JSON privé inclut le profil dans `manager_documents`, l’adresse d’inscription dans `account_contact` et les messages propres au manager dans `contact_messages`. L’adresse d’inscription n’apparaît pas dans la liste des utilisateurs. Les anciens messages reçus avant connexion restent conservés dans l’administration et ne sont pas rattachés rétroactivement à un compte.

## Atelier quotidien et saison

La vue d’ensemble réunit les priorités de tous les clubs privés : fraîcheur, fatigue dans le format explicitement choisi, notes et joueurs suivis, calendrier et incidents vacances. Les liens choisissent le club concerné avant d’ouvrir sa rubrique. Les préférences d’alertes sont privées ; les notifications du navigateur demandent un geste et une autorisation, fonctionnent seulement avec le tableau ouvert et n’envoient aucun mail.

**Saison & calendrier** conserve les matchs, séances et rappels, leurs dates avec fuseau, importance, état, notes et joueurs prévus. Un bouton lit les rencontres Classic, puis un second les ajoute au calendrier. Les rencontres déjà ajoutées sont préservées ; les dates inconnues sont signalées. Ce planning ne transmet aucun ordre au jeu et ne simule aucune récupération.

Dans **Optimisation → XV & banc**, le laboratoire permet de verrouiller un poste, imposer un titulaire, exclure un joueur, calculer les places restantes et conserver jusqu’à vingt scénarios nommés par club. Le terrain est interactif et utilisable au clavier ; la couverture du banc reste indicative. La comparaison distingue des objectifs ou observations non comparables. L’application d’un XV reste locale et vérifie que la composition et l’observation n’ont pas changé.

**Académie** rapproche objectifs individuels, générations, variations et dévoilements, avec dates et sources. Deux observations contradictoires au même instant ne deviennent pas une progression. Les séances réalisées sont déclarées manuellement et comparées au planning ; le dernier export n’est pas reconstruit en historique.

Dans **Séances planifiées et réalisées**, choisir un créneau renseigné reprend sa saison, sa semaine, son numéro et sa compétence. La date réelle reste vide et obligatoire ; le manager vérifie puis enregistre la séance. Aucune déclaration n’est automatique. Les tableaux de joueurs recherchent aussi par identifiant, sans tenir compte des accents, de la casse ou des espaces répétés ; les compétences connues sont triées numériquement et les inconnues restent à la fin dans les deux sens.

**Analyse des matchs** permet de rattacher explicitement les matchs à un club, un côté et un adversaire, puis de regrouper les rencontres par adversaire, saison et type Club/U20/NT. Couverture et dénominateurs restent visibles. **Stade & finances** conserve des projets avec capacités, coûts unitaires saisis, trésorerie et réserve, sans tarif ni rentabilité inventés. Un brouillon de stade modifié est averti lorsque de nouvelles données arrivent.

Les dossiers adversaires présentent une matrice de quatre zones et cinq types d’attaque. Chaque cellule donne un nombre et un pourcentage parmi les actions adverses classées de sa zone, dont le total est affiché. Une zone sans observation ne donne aucun pourcentage. La couverture générale porte sur tous les événements des matchs retenus, pour les deux équipes.

Le planning, le XV, le calendrier et les notes protègent les brouillons lors des changements de rubrique ou de club et de la déconnexion. Les champs sont bloqués pendant leur sauvegarde. Un conflit entre onglets conserve le brouillon à l’écran sans écraser la version enregistrée ; le bouton de relecture la recharge explicitement après confirmation. Relevez vos choix avant ce remplacement pour les reprendre. Les brouillons ne sont pas sauvegardés automatiquement et un départ confirmé les abandonne.

**Mon profil** personnalise aussi la palette, les initiales et l’emblème de chaque club sélectionné, indépendamment du profil du manager. Le formulaire de retour de chaque écran conserve des retours privés ou explicitement partagés avec l’administrateur ; **Contact & idées** fournit la boîte de contact dédiée. L’administrateur voit le contenu volontairement partagé, pas les bases des autres managers via l’interface. Les documents de travail figurent dans `manager_documents` de l’export JSON et dans les sauvegardes privées du VPS. Voir la [méthodologie de l’atelier](docs/workbench-methodology.md).

## Optimisation

Le centre **Optimisation** calcule un bilan pour un club ou tous les clubs présents dans l’espace privé du manager. Trois objectifs de composition : performance, récupération ou développement. L’affectation du XV maximise un indice d’affinité expliqué, sans doublons, avec un seuil d’énergie réglable et les indisponibilités connues. Les compétences manquantes ne sont jamais devinées. Le banc proposé reste à vérifier selon les remplacements souhaités.

Les recommandations couvrent effectif, académie, entraînement, saison, stade et qualité des données. Le programme proposé pour l’académie complète les créneaux libres sur les semaines retenues ; il conserve les cases déjà remplies et les semaines passées. Les observations de matchs proviennent de la bibliothèque du manager et affichent leurs dénominateurs et leur couverture. Elles ne prédisent pas les résultats.

Les propositions et leur méthode sont consultables avant sauvegarde. Seul le club sélectionné dans l’application peut recevoir un XV ou un programme, après confirmation explicite. Ces écritures concernent uniquement l’outil. Le bilan peut être exporté sans clé API. Les paramètres d’énergie distinguent pourcentage premium jusqu’à 110 et niveau 1–11 ; un format ambigu est signalé avant d’appliquer un filtre. Voir `docs/optimization-methodology.md`.

## Mode vacances

La rubrique réunit les compositions de match à préparer à l’avance, la composition par défaut et le suivi daté par club. Deux modes : préparer des propositions à relire ou les envoyer automatiquement pendant la période autorisée. Tout démarre désactivé ; chaque manager choisit ses dates, son objectif, le format et le seuil d’énergie, les exclusions et les rôles de capitaine/buteur. Les clubs simplement suivis ne peuvent pas recevoir d’ordres.

Un aperçu présente les joueurs et les changements avant envoi. Le serveur relit le propriétaire, l’effectif, l’échéance officielle et la composition distante, puis vérifie le résultat après le POST chiffré. L’API actuelle observée renvoie parfois 23 places et un mode de tactiques basic sans zones, contrairement à la documentation historique. Ce format exige un premier envoi manuel confirmé pour être utilisé automatiquement. Les tactiques et références de remplacement existantes sont conservées ; une référence devenue incohérente bloque l’envoi.

Les clés développeur `d`, `dk` et le paramètre `IV` associé sont nécessaires pour les envois chiffrés. Ils se configurent dans Connexion & données, restent chiffrés au repos et ne sont pas renvoyés au navigateur. Une lecture réussie sans IV ne prouve pas la capacité d’envoi. Si Classic ne fournit pas d’échéance pour un match, enregistrez d’abord sa composition dans le jeu ; l’outil n’invente pas une échéance depuis l’heure du coup d’envoi.

Le worker du VPS, activé par `BRT_VACATION_WORKER=1`, vérifie les règles toutes les quinze minutes après le passage précédent, dans le processus unique du service. Les appels Classic sont espacés et séquentiels. Journal et alertes restent dans l’espace privé ; aucun mail n’est envoyé par ce module. Arrêt par club et arrêt de tous les clubs : une requête déjà partie ne peut être annulée. Une coupure après envoi suspend le club et nécessite une relecture ou une validation explicite de l’état actuel ; aucun POST n’est rejoué aveuglément après un redémarrage.

L’autorisation d’un pilotage entièrement autonome par l’éditeur n’est pas confirmée. Ce module ne remplace pas la connexion au jeu exigée pour l’activité du compte. Les entraînements restent manuels. Voir `docs/classic-vacation-api.md` et `docs/vacation-methodology.md` pour les limites et contrôles.

## Calculs et limites

- Projection WC : règle personnelle de `ctr_ya.sql`, pas une règle générale d'éligibilité officielle.
- Les compétences inconnues ne sont ni estimées ni converties en zéro.
- Affinités par poste : moyennes pondérées explicables, pas une simulation du moteur.
- Stade : ratios 22/39/30/8/1 % du classeur ; multiplicateur modifiable, sans prévision de rentabilité.
- Matchs : clés `(type,id)`, 0 club / 1 U20 / 2 NT. Les zones sont relatives à chaque équipe. Les commentaires API sont classés uniquement lorsqu'une règle textuelle explicite correspond ; ces résultats sont **estimés** et leur couverture est affichée. L'import d'événements déjà classés utilise les champs `field`, `possession`, `att`.
- Les fonctions PostgreSQL de reclassement, le parseur PHP et les requêtes d'entraînement appelés par les scripts n'étaient pas joints. Une équivalence exacte avec tous les anciens résultats de Franck ne peut donc pas être certifiée.
- Les plannings et le XV des écrans historiques restent des préparations locales. Seule la rubrique Mode vacances peut transmettre une composition dans Classic, après validation ou selon une règle explicitement activée. Les tactiques existantes sont conservées ; les entraînements et transferts ne sont pas modifiés.

## Développement

Python 3.12+, Node 22.12+.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:BRT_PASSWORD='<mot de passe initial fort>'
$env:BRT_SECURE='0'
.\.venv\Scripts\python.exe -m uvicorn server.main:app_factory --factory --host 127.0.0.1 --port 3042
```

Le mot de passe initial n'est requis que pour créer la base. Ne pas le commettre. Construire l'interface avec `npm ci` et `npm run build` dans `web/`. Le serveur sert `web/dist`.

Tests : `.\.venv\Scripts\python.exe -m pytest -q`. Les tests utilisent des bases temporaires et n'appellent pas le jeu.

### Configuration des formulaires

| Fonction | Variables serveur | Comportement |
| --- | --- | --- |
| Inscription | `BRT_REGISTRATION_ENABLED` | `1` par défaut ; `0` ferme les inscriptions publiques. |
| CAPTCHA | `BRT_TURNSTILE_ENABLED`, `BRT_TURNSTILE_SITE_KEY`, `BRT_TURNSTILE_SECRET_KEY` | Activé avec `1`. Seule la clé de site est publique ; la clé secrète reste côté serveur. |
| Domaine et cookies | `BRT_PUBLIC_URL`, `BRT_SECURE` | Le domaine attendu du CAPTCHA vient de l’URL publique ; la production utilise HTTPS et les cookies sécurisés. |
| Notification du contact | `BRT_CONTACT_TO`, `BRT_SMTP_HOST`, `BRT_SMTP_PORT`, `BRT_SMTP_FROM`, `BRT_SMTP_USER`, `BRT_SMTP_PASSWORD` | Destinataire fixe côté serveur. Port 587 par défaut avec STARTTLS ; TLS direct au port 465. Identifiant et mot de passe SMTP doivent être fournis ensemble si une authentification est nécessaire. |

La connexion, l’inscription et le contact utilisent Cloudflare Turnstile lorsqu’il est activé. Le serveur vérifie le jeton, le domaine et l’action attendue après les limites de requêtes, avant le traitement du formulaire. Un jeton consommé, expiré ou refusé doit être renouvelé. Une configuration activée mais incomplète bloque l’opération ; les clés de démonstration sont refusées lorsque `BRT_SECURE=1`. Les erreurs du fournisseur ne sont pas renvoyées avec les jetons ou secrets. Sans activation, le navigateur confirme le mode désactivé auprès du serveur ; il ne décide pas seul de contourner la vérification.

Ne conserver aucune valeur secrète dans le dépôt. Voir le [guide de déploiement](docs/deployment.md) pour les paramètres, les sauvegardes et les vérifications à effectuer sur votre installation. Les journaux d’exploitation et informations personnelles ne font pas partie du dépôt public.

Photos, créations BRT, auteurs et licences : [visuels](docs/visual-assets.md) et [marques des clubs](docs/rugby-club-assets.md), également accessibles dans les crédits de l’interface.


## Retour de Franck du 31 octobre — version 2.5

- Conseils d’effectif : couverture des compétences, forces et faiblesses relatives, profils et besoins individuels, forme/énergie/blessures explicites. Étoiles cumulées et génération indicative pour les jeunes ; aucun seuil d’exclusion automatique à 29 ans.
- Académie : projection sur une à quatre saisons, cibles par compétence, hypothèse +0,20 et plafond 13,99, valeurs14 et inconnues préservées ; ni IGT ni maintien réel en académie prédits.
- Sélections privées U20/NT : rattachement avec vérification du sélectionneur, identifiants distincts des clubs, observations, XV local et progression. Suspension réversible du suivi avec conservation de l’historique.
- Préparation du prochain match : calendrier Classic et jusqu’à cinq rencontres documentées de l’adversaire, parmi les vingt dernières retournées. Côtés, dates, couverture et dénominateurs conservés. Le drapeau officiel botmatch (deux bots) est exclu ; aucun résultat ni tactique n’est inventé.
- Tutoriel enrichi pour chaque parcours.

