# Compositions Classic : contrat API et garde-fous

Documentation officielle consultée le 30 octobre 2026 : [API Classic](https://www.blackoutrugby.com/game/help.documentation.php?category=35&question=329), sections « Encrypted Requests », « Writing to the API », « Fixtures », « Lineups (Reads) », « Lineups (Writes) » et « Bulk Downloads/Updates ». Les contrôles locaux emploient des données synthétiques et `httpx.MockTransport` ; aucun envoi réel de composition n’a servi à valider cet adaptateur.

Une lecture autorisée d’un club de test et du [formulaire officiel de composition](https://www.blackoutrugby.com/game/club.lineup.php?next=1), le même jour, montre un écart avec les exemples API publiés : `b8` existe dans la réponse réelle et le formulaire officiel propose huit places de banc. La réponse réelle en mode `basic` n’a pas de `zone1` à `zone4`. Aucun formulaire n’a été soumis. Le code conserve ce format contemporain ; son acceptation par le POST API doit encore être confirmée par un envoi manuel demandé par le manager et sa relecture. Un schéma contemporain ne devient pas éligible à l’envoi automatique avant cette confirmation pour le club concerné.

## Identifiants et chiffrement

Le développeur obtient dans son compte Classic un identifiant, une clé développeur et un IV. L’IV accompagne les identifiants développeur ; ce n’est ni un mot de passe manager ni la clé `mk`. Copier la valeur fournie par Classic dans **Connexion & données**. Le code utilise la valeur littérale en UTF-8, comme les exemples Python/Java officiels : clé AES de 16, 24 ou 32 octets, IV de 16 octets. Une valeur hexadécimale ou Base64 ne doit pas être inventée ou décodée automatiquement.

La documentation demande de protéger la clé développeur et de chiffrer la requête dans l’application. Elle décrit des exemples en clair pour les tests seulement. Les écritures de l’outil exigent donc l’IV et n’ont aucun repli en clair. Le caractère « closed source » mentionné dans la documentation est une condition de distribution à vérifier par le propriétaire ; cette note ne certifie pas le statut de distribution du dépôt.

Les requêtes passent par HTTPS. L’écriture utilise `POST https://classic-api.blackoutrugby.com/?d=<identifiant>` et le champ de formulaire `er`, qui contient une chaîne URL-encodée chiffrée en AES-CBC avec padding nul puis encodée en Base64. `m`, `mk`, le type de requête et le contenu sont à l’intérieur du texte chiffré ; ni la clé AES ni l’IV ne sont transmis. Les lectures utilisent également `er` lorsque l’IV est configuré. Les lectures historiques sans IV restent compatibles avec l’import existant ; cela n’autorise aucun POST sans IV.

## Lecture et format canonique

`ClassicClient.read_lineup(team_id, fixture_id='0')` appelle `r=lu`, `teamid`, `fixtureid`. `0` désigne la composition par défaut. La réponse JSON documentée est un tableau `lineups` contenant les postes `p1` à `p15`, le banc `b1` à `b7`, les rôles, tactiques et substitutions. Le client exige les paramètres privés complets et vérifie l’identité du club et du match.

Le résultat interne contient `team_id`, `fixture_id`, `payload`, `fingerprint`, `schema`, `deadline` et `tactics_deadline`. Les deux échéances sont converties depuis les dates ISO 8601 munies de leur décalage vers UTC. Une date sans fuseau ou un ancien entier « BRT timestamp » est refusé ; les champs `deadline_local` ne sont pas utilisés. Une collection de compositions vide renvoie `None`. Un refus API reste un refus : il n’est pas réinterprété comme une absence, car il peut aussi signaler un problème de droits.

`ClassicClient.list_fixtures(team_id)` appelle `r=f&future=<club>`. Il renvoie une liste triée contenant `id`, `team_id`, `home_team_id`, `away_team_id`, `competition`, `match_start` (ISO 8601 UTC). Il vérifie que le club participe à chaque match. Le calendrier ne contient pas d’échéance de composition documentée.

La documentation indique qu’aucun objet de composition n’est renvoyé lorsqu’aucune composition n’a été enregistrée avant l’échéance ; la composition par défaut apparaît après celle-ci. Le contrôle réel d’un match futur sans composition propre a renvoyé un refus API, alors que le formulaire du jeu affichait une préparation issue du défaut. Copier le contenu par défaut fournit un modèle, mais ne fournit pas une échéance future fiable. Le service doit donc bloquer l’envoi de ce match tant qu’il ne dispose pas d’une échéance fiable issue de Classic. Il ne faut pas déduire arbitrairement cette échéance du coup d’envoi. Le manager peut enregistrer une première composition directement dans Classic, puis actualiser l’outil.

## Écriture complète

`write_lineup(team_id, fixture_id, payload, *, before_send=None)` autorise uniquement une composition de club senior complète. `validate_lineup_payload` renvoie un dictionnaire de valeurs canoniques sous forme de chaînes. `lineup_fingerprint` calcule son SHA-256, indépendant de l’ordre des clés et de la représentation initiale entier/chaîne, incluant le huitième remplaçant lorsqu’il existe.

`lineup_schema(payload)` distingue `classic-22-zones` (exemple API publié), `classic-23-basic` (format observé en lecture), `classic-23-zones` et `classic-22-basic`. Le schéma décrit la taille et la présence de zones, indépendamment du mode tactique actif. La preuve d’un envoi manuel confirmé pour le même club et schéma est requise par le service avant l’automatisation de tout schéma autre que `classic-22-zones`.

| Données | Champs POST |
| --- | --- |
| Titulaires | `1` à `15`, contrairement aux champs de lecture `p1` à `p15` |
| Banc | `b1` à `b7` dans la documentation ; `b8` est conservé et transmis lorsqu’il existe dans la réponse actuelle, soit **22 ou 23 joueurs** |
| Capitaine, buteur et leurs suppléants | `captain`, `kicker`, `captain1`, `captain2`, `kicker1`, `kicker2` |
| Remplacements par poste | `r1p1` à `r1p15`, `r2p1` à `r2p15` |
| Tactiques globales | `mode`, `defense`, `intensity`, `dropgoals`, `pickandgo`, `driving`, `expansive`, `creative`, `kicking`, `kickfortouch`, `upandunder`, `discipline` |
| Zones | Les huit dernières tactiques, suffixées `1` à `4` |
| Substitutions | `subreplaceN`, `subwithN`, `subminuteN`, `subscenarioN`, `submarginN`, `subenabledN` |

Les références de joueurs sont des identifiants, pas des numéros de poste. Tous les joueurs sont distincts ; capitaine et buteur principaux sont titulaires. Un rôle de secours à `0` reste non renseigné. Toute référence non nulle doit appartenir aux joueurs sélectionnés, y compris dans une substitution désactivée : le code ne supprime pas silencieusement une règle. Les substitutions sont renumérotées sans interruption à partir de 1, avec leurs six paramètres et leur ordre. Une condition inconnue empêche la lecture pour éviter de l’effacer lors d’un futur envoi.

Les tactiques globales sont obligatoires. La documentation demande les quatre zones même en mode `basic`, mais la lecture réelle peut les omettre toutes dans ce mode : l’adaptateur accepte cette absence complète et n’invente aucune valeur. En mode `zone`, ou dès qu’une zone est présente, les quatre zones complètes sont requises. Le mode de lecture `zoned` est normalisé en `zone`, valeur montrée dans les écritures officielles. Les quatre types d’attaque doivent totaliser 100. Les exemples officiels comportent un reste implicite de jeu au pied territorial : touche + chandelle peuvent totaliser moins de 100. Le champ de lecture zonal `kickforterritory` est contrôlé contre ce reste ; aucun champ d’écriture non explicitement documenté n’est ajouté pour le transmettre. Les valeurs existantes de touche et chandelle sont conservées.

Les champs d’authentification, `update`, `default`, `saved`, `delete`, `youth`, `nat`, `u20`, les noms libres et les places au-delà de `b8` sont refusés dans le payload. L’adaptateur ajoute lui-même `r=lu&update=1`. Il transmet `b8` lorsqu’il existe : l’omettre aurait supposé sans preuve que Classic le conserverait. La composition par défaut se met à jour en ciblant explicitement `fixture_id='0'` ; l’option Classic permettant de modifier simultanément match et défaut n’est pas exposée. Les entraînements restent des préparations locales : aucun endpoint d’écriture d’entraînement n’est implémenté.

## Confirmation, concurrence et arrêt

La réponse générale documentée est `status: Ok` ou `status: Failed`. La documentation ne donne pas de schéma exhaustif des résultats partiels d’une écriture. Après l’échéance des joueurs, Classic peut accepter seulement les tactiques pendant une heure supplémentaire. Un `Ok` renvoie donc seulement `{'status':'submitted','requires_verification':True}`. Le service doit relire la composition et comparer son empreinte avant de déclarer l’envoi confirmé.

Un timeout, une redirection, un statut HTTP inattendu, une réponse trop grosse ou JSON inexploitable après POST produit `ClassicWriteUncertain`. Aucun POST n’est automatiquement rejoué. Un refus explicite Classic produit `ClassicError` sans recopier le message distant, qui pourrait contenir des données sensibles. Ni les URL, ni les corps, ni les clés ne sont journalisés.

Toutes les requêtes GET et POST partagent un verrou process compatible avec plusieurs boucles asyncio et plusieurs threads. Un intervalle conservateur de trois secondes après chaque requête est conservé, même au-delà du démarrage. Les redirections sont refusées, le timeout HTTP reste 25 secondes et les réponses sont limitées à 8 000 000 octets. Le déploiement doit garder un seul processus applicatif : le verrou ne coordonne pas plusieurs workers ni plusieurs instances.

Le callback synchrone optionnel `before_send` s’exécute après l’attente du verrou et de la temporisation, immédiatement avant le transport HTTP. Il permet au service de revérifier arrêt, révision des règles, période, échéance et validité de l’aperçu. Ses exceptions remontent intactes et empêchent l’envoi. Un arrêt après le départ effectif d’un POST ne peut pas annuler une requête déjà reçue par Classic ; son résultat doit rester à vérifier.
