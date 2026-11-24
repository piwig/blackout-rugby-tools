# Audience BRT dans Vigie

Statut : validé par Pierig le 24 novembre 2026 : « Oui, réalise et publie ce
raccordement ». Aucune collecte BRT activée au moment de cette validation.

## Intention et périmètre

Savoir si BRT attire des visiteurs, quelles rubriques sont consultées et si les
présentations communautaires apportent du trafic. Utiliser l'installation
Umami/Vigie existante, sans abonnement ni campagne payante. Les mesures commencent
à l'activation ; elles ne reconstituent pas les visites passées et ne comptent pas
des personnes identifiées, des comptes actifs ou des actions sportives exécutées.

## Approche proposée

Le raccordement existant Umami → Vigie est adapté. Ajouter seulement BRT au
registre Audience, avec la collecte SEO/IA désactivée pour ce projet.

Un simple script automatique compterait surtout la racine de cette application
React, dont les rubriques ne changent pas l'URL. Les journaux serveur ne décrivent
pas davantage les écrans consultés et mélangent requêtes techniques et visites.
La proposition est donc une mesure manuelle des écrans, avec une liste fermée de
chemins et de titres génériques, puis les agrégats 7/30 jours de Vigie.

## Collecte et confidentialité

- Mesurer uniquement les écrans effectivement affichés : accueil public,
  inscription, installation initiale et rubriques de navigation connues.
- Émettre des chemins synthétiques fixes et des titres génériques ; ne jamais
  lire les noms de clubs, joueurs, managers ou données importées pour les mesures.
- Ne transmettre aucun identifiant de compte/club/joueur/match, texte saisi,
  mot de passe, jeton, rapport, détail de formulaire ou propriété utilisateur.
- Désactiver l'automesure Umami. Construire entièrement chaque payload manuel,
  sans URL réelle, query, hash ou titre du document. Provenance : domaine HTTP(S)
  externe seulement, sans chemin, query, hash ou credentials ; vide en interne.
- Pas de suivi des clics, formulaires, erreurs, sessions rejouées ou événements
  individuels dans ce lot. Pas de profil utilisateur ni liaison avec les comptes.
- Respecter Do Not Track et le choix local de désactivation. Exclure les écrans
  d'un administrateur connecté ; une visite publique avant identification peut
  toutefois rester comptée. Les contrôles de recette doivent être distingués.
- Ajouter une explication brève et un choix de désactivation dans les quatre
  langues. Ne pas présenter « sans cookie » comme une absence de traitement :
  Umami traite techniquement les requêtes/IP/User-Agent pour produire les agrégats.
- La collecte est facultative : indisponibilité, bloqueur ou refus ne doit jamais
  ralentir ni empêcher l'utilisation de BRT.

## Mise en place

Créer, après vérification de l'existant, un site et une équipe Umami dédiés à BRT.
L'équipe appartient à l'administrateur ; un lecteur distinct dispose uniquement
de View only global et team-view-only dans cette équipe. Aucun partage public et
aucun élargissement des lecteurs d'autres projets. Les secrets restent dans les
fichiers privés du serveur avec permissions adaptées ; seul le site ID public
peut parvenir au navigateur.

Configurer un chargement unique du tracker et une déduplication des vues
consécutives, y compris sous React StrictMode et lors d'un chargement tardif.
A → B → A doit compter trois vues ; un rafraîchissement des données sur A n'en
ajoute pas une. Autoriser précisément l'origine du collecteur dans la CSP.

Ajouter BRT au registre serveur sans remplacer les projets existants, synchroniser
la configuration puis vérifier les agrégats dans Vigie. Essayer le connecteur
Audience ; signaler séparément un défaut de connexion de ce connecteur si le
dashboard et la collecte fonctionnent.

## Contrôles et publication

Tests ciblés sur les payloads, les exclusions, le choix local, les doublons et les
échecs ; suites BRT requises et build. Revue indépendante. Sauvegarde et retour
arrière avant publication. Dans Chrome, vérifier une vraie vue et les données
émises ; dans Umami/Vigie, vérifier leur réception et les droits limités du
lecteur. Un appel JavaScript résolu ne prouve pas la réception.

Conserver les preuves et les agrégats opérationnels dans les dossiers privés,
jamais dans Git. Le déploiement doit préserver les données, la connexion, le
CAPTCHA et les réglages existants. Le retrait du tracker/config BRT doit permettre
un retour arrière sans effet sur les autres projets.

## Présentation communautaire associée

Cible demandée : francophone et internationale, Classic uniquement. Préparer des
annonces FR/EN factuelles avec lien vers BRT et compte distinct de celui du jeu.
Rechercher les espaces externes actuels et lire leurs règles. Ne publier que dans
un espace adapté qui autorise le partage ; pas de publicité payante, diffusion
massive, message personnel ou adhésion automatique. Les règles Classic lues le
24 novembre interdisent la publicité dans le lounge des applications tierces :
une discussion existante sur un autre outil ne vaut pas permission pour BRT.

## Décisions proposées par Codex

Audience seule ; vues de rubriques sans événements métier ; exclusion des admins
connectés ; provenance réduite au domaine ; opt-out local ; installation existante
et lecteur isolé. Ces choix font partie du cadrage validé.
