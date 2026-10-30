# Mode vacances : méthode et limites

Le service `server/vacation.py` prépare une composition ou la transmet à Classic uniquement après une validation manuelle ou dans une règle automatique explicitement activée. Chaque base privée possède ses règles, aperçus, preuves de format et journaux. Aucun compte existant n’est activé par migration.

## Sélection et formats Classic

L’affectation réutilise les affinités et l’algorithme de l’optimisation locale. Le mode récupération favorise l’énergie observée ; le développement favorise les joueurs plus jeunes. Les choix ne simulent pas le moteur du jeu. Chaque joueur sélectionné doit avoir une énergie exploitable, une disponibilité médicale explicitement confirmée et une affinité calculable. Les exclusions, le seuil et le format d’énergie s’appliquent aussi au banc. Le format automatique d’énergie ne permet pas d’envoyer : l’utilisateur doit choisir pourcentage ou niveau 1–11, faute d’un indicateur premium suffisamment vérifié. Le niveau est converti approximativement par multiplication par dix.

La composition distante détermine le format. Le contrat historique contient 15 titulaires et 7 remplaçants, avec toutes les tactiques de zone. La lecture réelle a également montré un huitième remplaçant (`b8`) et le mode basique sans zones. Lorsque `b8` est présent, l’aperçu calcule, affiche et transmet les 23 joueurs. Il ne supprime pas ce champ. Sans `b8`, la place locale 23 est exclue explicitement avec le nom et l’identifiant du joueur dans l’aperçu.

Les formats différents du contrat historique exigent une première transmission manuelle, suivie d’une relecture identique, avant de permettre un envoi automatique. Cette preuve est privée et liée au club, au manager Classic et au format. Elle ne constitue pas une garantie générale de stabilité de l’API. Aucun envoi réel n’est réalisé dans les tests.

Les tactiques et les références des remplacements sont conservées. Si un capitaine, buteur ou remplacement pointe vers un joueur retiré, l’aperçu bloque ; il ne supprime pas silencieusement cette référence. La couverture des postes par le banc reste une limite de l’heuristique.

## Deux phases avant toute écriture

1. Lire le membre authentifié et le propriétaire actuel du club, le calendrier, l’effectif et la composition Classic. Un club seulement suivi ne donne aucun droit d’écriture.
2. Conserver un aperçu de dix minutes avec empreintes de l’effectif et de la composition, révision des règles et échéance officielle. Le serveur conserve seul les empreintes et le contenu à envoyer.
3. À la confirmation, relire les mêmes données et refuser toute différence. Une composition par défaut n’exige pas d’échéance de match ; un match nécessite une échéance officielle connue et un coup d’envoi futur. Une absence d’échéance demande d’enregistrer d’abord la composition dans le jeu.
4. Enregistrer une tentative en SQLite avant le POST. Vérifier à nouveau l’arrêt, les règles et l’échéance après l’attente du limiteur réseau, immédiatement avant transmission. Relire Classic après le POST ; seule une empreinte identique confirme l’envoi.

Le verrou asynchrone par espace et la réservation atomique SQLite empêchent les doublons de travailleurs concurrents. Une application déployée doit utiliser un seul processus worker : la reprise après redémarrage transforme les envois laissés par un ancien processus en résultats incertains. Une demande d’arrêt ne peut pas annuler un POST déjà transmis.

Classic ne fournit pas de mise à jour conditionnelle liée à l’empreinte lue. Une modification externe dans le bref intervalle entre la dernière lecture et le POST ne peut donc pas être exclue totalement. Les relectures et le journal rendent les conflits observables, sans promettre une transaction distribuée.

## Dates, automatique et intervention humaine

Une règle concerne un club, une période avec fuseau horaire d’au maximum 56 jours et une anticipation de 2 à 168 heures. Le worker passe toutes les quinze minutes. Le mode préparation crée seulement des aperçus ; le mode automatique peut les envoyer. La fin de période désactive la règle. Le bouton d’arrêt invalide aussi les aperçus déjà préparés.

Une composition déjà présente dans Classic est préservée par défaut. La gestion automatique de compositions existantes exige une option explicite. Après un envoi confirmé, une modification distante est considérée comme une intervention humaine et ne doit pas être écrasée. Une rencontre confirmée n’est pas réenvoyée à chaque passage du worker.

La période maximale de 56 jours ne remplace pas la connexion périodique au jeu. L’autorisation de l’automatisation par l’éditeur reste à confirmer ; l’outil n’en affirme pas la conformité. Il ne modifie ni entraînements, ni transferts, ni finances.

## Incertitude et reprise

Une interruption après le début d’un envoi, une relecture différente ou un envoi retrouvé au redémarrage suspend le club et désactive sa règle. Le service ne réessaie jamais aveuglément.

La réconciliation relit la propriété et la composition sans effectuer de POST. Une composition identique confirme l’envoi. Sinon, elle présente la composition actuelle et demande une acceptation explicite. Cette acceptation relit encore Classic : si l’empreinte a changé, une nouvelle revue est nécessaire. Un ancien aperçu réconcilié ne peut plus être envoyé. Une nouvelle proposition et une nouvelle confirmation restent possibles après cette revue ; réactiver le mode automatique exige une action distincte.

Le journal est borné à 300 événements par espace et les aperçus ordinaires à 100, avec conservation des résultats incertains. L’état renvoie toujours tous les résultats incertains et les envois en cours, puis les 20 autres aperçus les plus récents : un incident ancien reste accessible pour réconciliation. Les clés, adresses privées du membre, corps de réponses d’erreur et exceptions techniques n’entrent pas dans ces journaux.

Les tests utilisent des bases temporaires et un serveur Classic simulé. Ils couvrent notamment isolation, propriété, seuils, données inconnues, dates, arrêt pendant lecture ou attente réseau, conservation des tactiques, formats 22/23, preuve manuelle, doublons, reprise et réconciliation après changement distant.
