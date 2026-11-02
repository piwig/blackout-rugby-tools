# Jour de match : comparer les deux feuilles

## Intention

Préparer les décisions tactiques une fois les compositions publiées, sur ordinateur et téléphone. L’accès « Jour de match » appartient au groupe « Préparer le match » et fonctionne pour chaque club, ses juniors, les U20 et les sélections nationales rattachées. Les demandes actuelles autorisent l’implémentation, les choix de détail, la publication GitHub et le déploiement VPS ; aucun nouveau cycle d’approbation de maquette n’est nécessaire.

## Approche retenue

Un écran dédié, utilisant l’adaptateur Classic existant, est préférable à un tableau supplémentaire enfoui dans l’analyse historique. Réécrire le script en le lançant côté serveur serait fragile et risquerait d’exposer ses identifiants ; son code original reste privé et n’est jamais exécuté. Une simple exportation serait insuffisante sur téléphone.

## Parcours et données

- Choisir l’équipe dans le sélecteur actuel. Pour un club, choisir seniors ou juniors ; U20/NT sont déterminés par l’identité locale. Actualiser les rencontres à venir, en choisir une, puis lire ses feuilles. Un champ ID/lien officiel permet aussi une rencontre précise. Tout lien est analysé, jamais téléchargé directement.
- Lire uniquement `f`, `t`, `lu`, `p`, avec le contexte Classic correspondant (`youth=1`, `u20=1`, `nat=1`). Contrôler que la rencontre appartient bien à l’équipe affichée. Aucun appel d’écriture, aucune tactique privée ni donnée brute confidentielle retournée au navigateur.
- Présenter les 15 postes et les huit places de banc dans leur ordre exact, les noms d’équipes, capitaines et buteurs. Par joueur : CSR, poids, taille, forme, énergie brute, expérience, agressivité, discipline ; les compétences ne sont pas nécessaires à cette comparaison.
- Un joueur absent de la réponse conserve sa ligne ; aucun décalage de postes. Une composition absente reste « non fournie » : aucun remplacement silencieux par le Default, aucune tentative de contourner sa publication. Un banc historique à sept joueurs laisse la place 23 explicitement absente.
- Si Classic refuse la lecture d’une feuille, ce côté reste « lecture impossible », sans supposer la cause ; l’autre feuille peut être consultée. Une réponse reçue avec une identité ou une population contradictoire rejette toujours le rapport complet.
- Lectures bornées : une rencontre, deux équipes, deux feuilles, au plus 46 joueurs par lots de 23. L’adaptateur garde son espacement global. Les exceptions amont et leurs URLs ne doivent pas exposer de clés.
- Repli du calendrier junior si Classic échoue sur `future+youth` : lire le calendrier du club puis vérifier au plus 50 identifiants de championnat avec `fixtureids+youth`. Ne jamais transformer une rencontre senior en junior sans cette confirmation. Trois requêtes maximum ; la liste de repli est explicitement partielle et la saisie d’un lien reste disponible.

## Calculs

Comparer première ligne (1–3), deuxième (4–5), troisième (6–8), pack (1–8), charnière (9–10), centres (12–13), triangle arrière (11/14/15), XV, banc et ensemble. Poids total du pack seulement si les huit poids sont connus. Pour chaque métrique, afficher le nombre de valeurs connues ; ne pas convertir une absence en zéro. Les moyennes des valeurs connues ne sont pas des valeurs complètes d’effectif.

Indice personnel ajusté : `CSR × (1 + 0.07 × (forme − 7)) × (1 + 0.02 × (expérience − 7)) × énergiePourcent / 100`, tronqué par joueur avant une moyenne entière. Inspiré du script fourni, non officiel, sans valeur de pronostic. Énergie à deux échelles : en auto, une valeur >11 établit un pourcentage pour CE joueur ; une valeur ≤11 reste ambiguë. Chaque côté peut choisir explicitement pourcentage ou niveau (niveau×10, approximation). Ne jamais déduire le format de tous les joueurs d’une sélection depuis un seul joueur. Valeur hors plage ou donnée manquante : indice inconnu. Tous les indicateurs affichent leur couverture ; aucun avantage global certain n’est déduit du CSR ou du poids.

## Échéances et fraîcheur

Utiliser les dates avec fuseau effectivement fournies par Classic pour les échéances de composition et de tactiques. Si absentes ou ambiguës, afficher « non fournie » et des repères séparés : composition H−3h05, publication H−3h, tactiques H−2h05. Ces repères ne sont jamais annoncés comme un verrou confirmé. Horaires affichés dans le fuseau du navigateur, avec date de lecture. Les caractéristiques de joueurs sont celles de la lecture actuelle, pas des valeurs historiques au coup d’envoi.

## Présentation, sécurité et validation

Cartes compactes comparant les deux joueurs d’un même poste sur mobile ; tableaux de synthèse accessibles avec unités et couvertures. Aucun défilement horizontal imposé pour comparer une paire sur 390px. Rafraîchissement manuel ; aucune interrogation permanente de Classic. Un échec conserve le dernier rapport affiché avec son horodatage et un message clair. Changer d’équipe/population efface les résultats en cours et ignore toute réponse tardive.

Accès connecté, CSRF, isolation des espaces et contrôle de l’équipe dans l’espace conservés. Requêtes limitées et réponses validées. Aucun fichier, identifiant, exemple de compte ou mail privé dans le dépôt public. Français, anglais, espagnol, italien ; aide intégrée. Tests de calcul, contrats API, refus d’accès, populations, données manquantes, rendu et parcours mobile, puis sauvegarde, déploiement et vérifications publiques/authentifiées. Version prévue : 2.13.0, affichage et santé cohérents.
