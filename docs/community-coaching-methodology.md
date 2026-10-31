# Critères du manager, rapports et navigation

## Intention

Rendre les décisions de composition et le suivi des joueurs plus personnels et mieux documentés. Les pistes communautaires servent à identifier des besoins ; les anciennes formules de forums ne deviennent pas des règles officielles du jeu.

## Critères de sélection

Le laboratoire de XV conserve un profil par défaut et permet des profils privés de coefficients par rôle. Chaque compétence a un poids explicite ; une compétence de poids nul n’intervient pas dans le calcul. Les compétences requises inconnues empêchent de calculer l’affinité du rôle, sans être remplacées par une moyenne.

Les profils sont nommés et conservés par club. Les scénarios gardent les coefficients utilisés, même si le profil est modifié ensuite. Deux scénarios utilisant des critères différents ne donnent pas un gain numérique présenté comme comparable. Les règles d’énergie, de disponibilité, de verrouillage et d’exclusion restent applicables. Aucun ordre de jeu n’est envoyé par cet écran.

## Rapports officiels et performances

Les instructions, rapports d’entraînement et statistiques de joueurs Classic sont des lectures sur le club autorisé. Chaque collecte vérifie le compte et le propriétaire du club auprès de Classic, puis présente un aperçu à confirmer. Ouvrir l’écran ne lance aucune lecture externe. Les observations conservées portent leur période, leur source et leur date de collecte. Un échec ne remplace pas les données déjà enregistrées ; un réimport identique au dernier relevé du même périmètre ne double pas les données. Un retour ultérieur à d’anciennes valeurs crée une nouvelle observation distincte.

Les ressources `ti` (instructions) et `ps` (statistiques) ont été vérifiées sur des réponses réelles. Le parseur `tr` suit la documentation JSON et des jeux de tests synthétiques ; les lectures réelles essayées pour ce lot ont été refusées par Classic. L’écran indique ce refus sans conclure à une absence d’entraînement. La disponibilité des rapports reste à confirmer pour les clubs concernés. Référence : [documentation officielle de l’API Classic](https://www.blackoutrugby.com/game/help.documentation.php?category=35&question=329), rubriques Training Instructions, Training Reports et Player Statistics.

Les séances prévues, déclarations manuelles et rapports officiels restent distincts. Une variation de CSR ou de compétence décrit une observation, sans prouver une causalité. Un rapport absent n’équivaut pas à une absence de progrès.

Les statistiques individuelles n’utilisent que des compteurs et dénominateurs connus. La ressource ne fournit ni minutes ni postes : aucun taux par 80 minutes ni ajustement par poste n’est calculé. `balltime` désigne le nombre de portées de balle, pas une durée. L’écran propose les compteurs bruts de carrière ou de championnat pour une saison explicite, leur couverture, le tri et la recherche. La carrière des joueurs actuels peut comprendre d’autres clubs. Le pourcentage de plaquages réussis utilise réussis / (réussis + manqués), seulement si les deux valeurs sont connues et le total positif. Les écarts exigent deux dates ordonnées et un périmètre identique ; une baisse est signalée comme révision du compteur, sans inventer une performance négative.

Les relevés sont privés et inclus dans l’export du manager. L’historique est paginé par vingt observations sans purge automatique. Les lectures concernent au plus 200 joueurs, par lots de 50. Les rapports sont bornés à 200 joueurs par phase et dix compétences distinctes par joueur. Une observation normalisée est limitée à 512 000 octets ; les données trop volumineuses sont refusées avant conservation ou décodage d’un ancien enregistrement. Les aperçus expirent après dix minutes et sont invalidés par un changement de compte, de clés ou de révision.

## Navigation

La navigation conserve un accès principal au tableau de bord et regroupe les outils : préparation des matchs, développement des joueurs, gestion du club, puis espace personnel et aide. Les groupes peuvent se replier ; un changement de page rend son groupe visible. Les sélections nationales ne voient pas les outils réservés aux clubs. Le menu mobile conserve fermeture, focus clavier et protection des brouillons.

## Validation et publication

Tests des coefficients invalides et partiels, scénarios historiques, conflits, accès entre managers, réimports et défaillances Classic. Recette sur bureau et mobile, quatre langues, chargement et erreurs. Les données réelles, secrets, captures de recette privées et journaux VPS restent hors du dépôt public. Sources validées poussées sur GitHub, sauvegarde puis déploiement et vérification de la version publique.
