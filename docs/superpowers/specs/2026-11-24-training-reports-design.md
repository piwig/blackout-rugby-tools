# Rapports d’entraînement importés et suivi vérifiable

## Objectif

Permettre à un manager de conserver et comprendre un rapport d’entraînement Classic reçu par mail, même lorsque la lecture API du rapport est indisponible. Réutiliser le carnet privé d’entraînement de BRT et préserver la distinction entre résultat fourni par une source et variation constatée entre deux relevés.

Le lot concerne les rapports, leur import et leur restitution. Il ne modifie pas les réglages sportifs dans Classic. Aucun message, nom, identifiant, chiffre ou fichier réel d’un compte ne doit entrer dans les sources, les tests ou la documentation publics. Les validations sur document réel restent dans les dossiers privés exclus de Git.

## Approches

1. **Import local HTML/EML avec aperçu**, puis conservation dans le carnet existant : fonctionne sans accès API supplémentaire et conserve les détails propres au rapport. C’est l’approche retenue pour ce lot.
2. Lecture API seule : déjà implémentée, mais insuffisante lorsque Classic refuse la ressource. Elle reste disponible et doit bénéficier des améliorations de restitution.
3. Synchronisation automatique de Gmail : imposerait une intégration et des droits supplémentaires pour un besoin que le fichier local permet de couvrir. Hors de ce lot.

Le choix technique est celui de l’agent : conserver FastAPI/Python et React/TypeScript, utiliser les bibliothèques existantes ou la bibliothèque standard, et ne pas ajouter de service distant.

## Import et identité

- Accepter un mail exporté en `.eml` ou son corps HTML dans une limite de taille explicite. Décoder les jeux de caractères et les parties MIME usuels ; ignorer scripts, styles, images, traceurs et pièces jointes non pertinentes, sans exécuter ni télécharger aucun contenu.
- Extraire saison/semaine, nom du club, identifiants et noms des joueurs, compétences collectives, CSR avant/après de chaque phase, changements de niveau, séances, entraîneurs et niveaux, énergie individuelle avant/après.
- Reconnaître explicitement le format pris en charge. Refuser un document vide, tronqué, contradictoire ou d’un format inconnu avec un message exploitable.
- Vérifier la destination parmi les clubs du manager et la concordance des indices d’identité disponibles (club et joueurs). Ne pas déduire un identifiant de club absent du mail ; expliquer la couverture et les éventuelles inconnues historiques.
- Un fichier importé ne prouve pas l’authenticité de son expéditeur. Sa provenance est présentée comme un mail importé ; elle reste distincte d’une lecture directe de Classic.
- Aperçu sans écriture, puis confirmation atomique liée au manager, au club et à la révision. Aucun appel Classic nécessaire pour lire un fichier local.
- Détection des doublons par contenu normalisé. Aucun écrasement silencieux d’un rapport différent pour une même période. La coexistence ou l’enrichissement de sources concordantes doit rester traçable et ne pas compter deux fois les gains.

## Modèle et calculs

- Conserver les entraîneurs, leurs niveaux et les séances pour les rapports API comme pour les fichiers, en acceptant l’absence de ces champs dans les anciens documents.
- Conserver les énergies textuelles du mail comme des libellés. Ne pas les convertir en pourcentages approximatifs ni les fusionner avec des niveaux numériques dont l’échelle n’est pas établie.
- Distinguer absence d’information, liste explicitement vide et absence de passage de niveau. « Aucun passage » ne veut pas dire « aucun progrès ».
- Calculer uniquement les différences arithmétiques connues : CSR collectif, individuel et total ; hausses, baisses et valeurs stables ; joueurs et séances couverts ; passages de niveau par phase.
- Contrôler, lorsque les deux valeurs existent, que le CSR de fin de collectif correspond au CSR de début d’individuel. Signaler une rupture au lieu d’additionner des étapes incompatibles ou de masquer un écart.
- Une baisse de CSR n’est pas assimilée automatiquement au vieillissement ; les changements de forme, les compétences révélées et les variations entre relevés restent des observations distinctes.
- Ne pas transformer le rapport en instantanés complets de caractéristiques : il ne contient pas toutes les compétences ni toute la forme des joueurs.

## Interface

- Ajouter un parcours d’import de fichier dans l’espace d’entraînement existant, avec fichier choisi, résumé de l’aperçu, destination, provenance, avertissements, confirmation et annulation.
- Présenter un bilan lisible par phase et un détail par joueur : séances, entraîneur/niveau, CSR avant/après, énergie et changements de niveau.
- Préserver la lecture des anciens rapports et le parcours API actuel ; expliquer clairement les données absentes et les différences entre relevé et rapport.
- Fournir les textes du produit dans les quatre langues existantes et une aide mise à jour. Vérifier l’affichage étroit et les états chargement/erreur/confirmation.

## Vérification et résultat attendu

- Tests synthétiques du parseur : HTML, EML multipart, encodage, accents, passages, absence de passage, décimales/intervalles inconnus, doublons, identités contradictoires, document partiel et contenu hostile sans effet externe.
- Tests des routes : isolation des managers, destination, limites, confirmation, révision concurrente, idempotence, conflit et conservation de l’historique.
- Tests des calculs : couverture, valeurs manquantes, continuité, somme des phases et absence de double compte.
- Tests de restitution, compilation TypeScript et contrôle visuel/parcours local si le navigateur est disponible ; signaler précisément tout contrôle impossible.
- Comparaison privée avec un rapport réel, sans incorporer ses données au dépôt. Mise à jour de la méthodologie avec ce qui a réellement été validé.

Le livrable est un lot cohérent de code, tests et documentation prêt à examiner dans le checkout isolé existant. Un déploiement éventuel viendra après ces validations et conformément aux autorisations applicables.

## Choix précisés après relecture du cadrage

- **Identité locale :** authentification BRT et destination club local autorisée obligatoires, sans appel ni clé Classic. Le nom du club dans le fichier doit correspondre au nom local après normalisation Unicode et des espaces ; un identifiant de club explicite contradictoire bloque l’import. Les joueurs absents de l’effectif actuel sont signalés, sans être assimilés à une autre équipe : un ancien rapport peut concerner des joueurs partis. L’aperçu indique que l’identité du mail est déclarative, et ne certifie pas l’expéditeur. Un ancien nom de club non reconnu exige une destination ou une donnée corrigée explicitement ; aucune correspondance approximative silencieuse.
- **Sources et doublons :** conserver les observations de mail séparément du rapport API et les identifier dans le sélecteur par période et source. Le même contenu de mail normalisé pour le même club est un doublon ; un contenu différent reste une preuve distincte et signale les désaccords sur les champs communs. Le bilan porte sur le rapport sélectionné, jamais sur la somme de plusieurs preuves de la même séance. Les conflits déjà bloqués par le parcours API ne sont pas transformés en écrasements. Une information nouvelle facultative peut être conservée comme enrichissement traçable, sans altérer la preuve d’origine ni accepter une contradiction sur les valeurs déjà connues.
- **Compatibilité :** schéma de rapport versionné ; identifiant Classic facultatif pour les mails, clé de stockage interne distincte. Les documents existants s’adaptent à la lecture sans réécrire leur contenu. Les champs facultatifs absents et `null` sont équivalents pour la comparaison sémantique ; l’ajout d’un champ de version ne doit pas créer de faux conflit ou doublon.
- **Énergie :** valeur typée séparant libellé textuel, niveau numérique et échelle non précisée. Les anciens champs numériques restent lisibles. Pas de différence chiffrée entre deux représentations incompatibles.
- **Couverture :** `null` signifie non fourni, `[]` une liste explicitement vide. Une mention explicite d’absence de passage est conservée comme telle. Les bilans affichent leur dénominateur ; le total des phases ne porte que sur des trajectoires connues et continues. Les autres sommes restent partielles, avec population et anomalie visibles.
- **Formats v1 :** HTML des rapports Classic en anglais et EML contenant ce HTML, y compris multipart, quoted-printable et base64 usuels. Le texte seul, les chaînes de mails transférés ambiguës et les autres langues non reconnues sont refusés clairement. Limites : 2 Mio avant et après décodage, 50 parties MIME, profondeur 8, 200 joueurs par phase, 10 compétences distinctes par joueur, document normalisé de 512000 octets maximum. Les identifiants de joueurs et les marqueurs de période/phases sont requis ; entraîneur, énergie ou passages non fournis restent inconnus.

Ces choix sont proposés par l’agent. La relecture a porté sur le cadrage et les points d’intégration existants ; aucune fonctionnalité produit n’est encore modifiée à ce stade.
