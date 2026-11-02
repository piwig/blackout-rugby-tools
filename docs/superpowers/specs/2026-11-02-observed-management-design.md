# Gestion fondée sur les observations

## Intention

Les retours d’un manager expérimenté demandent de retrouver les informations concrètes utiles de BRM : effectifs complets et triables, commentaires juniors, étoiles de recrutement non plafonnées artificiellement, notes et contexte des quatre derniers matchs. Les observations doivent rester distinctes des modèles personnels de BRT.

## Choix de réalisation

Étendre les écrans existants, sans nouvelle entrée de sidebar ni moteur de recommandation. Une refonte générale ferait perdre les parcours validés ; recopier BRM introduirait ses défauts de fraîcheur et de plafonnement. Le choix du constructeur est donc une amélioration progressive de l’application React/FastAPI existante.

1. Effectifs : conserver la vue essentielle et proposer une vue complète, triable, commune aux seniors et juniors. Inclure les caractéristiques observées, la date/source, les évolutions avant/après connues et les commentaires privés à droite. Réutiliser l’édition de fiche existante. Une valeur absente reste inconnue ; les étoiles sont affichées telles qu’importées, sans plafond127 et sans corriger silencieusement un ancien relevé.
2. Jour de match : après lecture d’une rencontre, un bouton lit les quatre derniers matchs terminés de chacun des deux participants. Conserver l’ordre et les lignes quand un rapport manque. Montrer équipes, dates, compétition, scores, météo fournie et notes collectives du reporter Classic. Les notes ne sont ni des fréquences tactiques ni des prédictions. Les échelles inconnues ne reçoivent pas de dénominateur inventé.
3. Clarté : afficher près des observations leur source et leur date ; afficher près des simulations leur nature personnelle et leurs limites. Les liens vers les performances observées restent dans le parcours existant. Juniors de club et sélection U20 restent deux contextes distincts.

## Contrats et limites

Lecture réseau bornée : fixture cible, historique20 maximum par participant, quatre derniers matchs terminés, reporter rs limité aux IDs sélectionnés et noms d’équipes par lots10. Identités et indicateurs de population vérifiés à chaque frontière. Doublons de fixture entre les deux historiques dédupliqués. Seniors/juniors/U20/national utilisent les sélecteurs explicites existants ; pas de repli d’une population sur une autre. Tout rapport incohérent est refusé ou signalé manquant sans masquer des données correctes voisines.

Scores et notes viennent du reporter, météo de la fixture. Un score entièrement absent peut être complété par la ressource de score Classic `ls` après confirmation de fin et contrôle de contexte ; sa source reste distincte des notes. Ce repli ajoute au plus huit lectures, dédupliquées par fixture. Sans correspondance météo vérifiée, conserver le code Classic et l’indiquer plutôt que choisir une icône arbitraire. Aucune donnée actuelle d’un joueur ne sera présentée comme une caractéristique historique. Pas d’écriture dans Classic, de nouvelle règle d’automatisation ni de changement de droits.

Les notes privées restent protégées par le parcours existant et sa comparaison de version. Les pages et requêtes asynchrones sont isolées par utilisateur/session/équipe/population/fixture. Un changement de contexte ignore les réponses tardives. Pas de clé, donnée de compte ni capture dans le dépôt public.

## Acceptation

Les valeurs600 et1000 étoiles restent intégrales, les inconnues restent en fin de tri et les commentaires sont accessibles au clavier. Les quatre lignes sont les dernières terminées, même si des notes manquent. Un score0 reste0 ; aucun rapport vide ne devient une performance nulle. Racines/équipes/fixture/population contradictoires refusées. Tests synthétiques significatifs, contrôle réel limité à notre accès propre en lecture, revue indépendante, build et i18n, publication atomique avec sauvegardes puis vérification publique et réponse au testeur.
