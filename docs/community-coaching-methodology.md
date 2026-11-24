# Critères du manager, rapports et navigation

## Intention

Rendre les décisions de composition et le suivi des joueurs plus personnels et mieux documentés. Les pistes communautaires servent à identifier des besoins ; les anciennes formules de forums ne deviennent pas des règles officielles du jeu.

## Critères de sélection

Le laboratoire de XV conserve un profil par défaut et permet des profils privés de coefficients par rôle. Chaque compétence a un poids explicite ; une compétence de poids nul n’intervient pas dans le calcul. Les compétences requises inconnues empêchent de calculer l’affinité du rôle, sans être remplacées par une moyenne.

Les profils sont nommés et conservés par club. Les scénarios gardent les coefficients utilisés, même si le profil est modifié ensuite. Deux scénarios utilisant des critères différents ne donnent pas un gain numérique présenté comme comparable. Les règles d’énergie, de disponibilité, de verrouillage et d’exclusion restent applicables. Aucun ordre de jeu n’est envoyé par cet écran.

## Consignes, rapports d’entraînement et statistiques

Les lectures d’instructions, de rapports et de statistiques via l’API vérifient le compte et le propriétaire du club auprès de Classic. Elles démarrent sur demande et présentent un aperçu à confirmer. Les observations conservées portent leur période, leur source et leur date de collecte.

Les ressources `ti` (instructions) et `ps` (statistiques) ont été vérifiées sur des réponses réelles. La couverture de `tr` (rapports) repose sur la documentation JSON et les tests synthétiques. Classic a refusé les lectures réelles essayées lors de la validation de ce parcours API. L’application signale le refus et conserve les observations précédentes. [Documentation officielle de l’API Classic, rubriques Training Instructions, Training Reports et Player Statistics](https://www.blackoutrugby.com/game/help.documentation.php?category=35&question=329)

Le parcours par fichier lit le HTML des rapports Classic en anglais ou le message EML qui le contient, jusqu’à 2 Mio avant et après décodage. Il utilise la session BRT et les droits sur le club local, sans clé ni requête Classic. Le nom déclaré doit correspondre au club sélectionné après normalisation Unicode et des espaces. Un identifiant explicite de club contradictoire bloque l’import. L’aperçu compare les joueurs du rapport au dernier effectif senior enregistré. Il signale les joueurs manquants. Sans effectif enregistré, leur présence reste inconnue et le manager peut confirmer le rapport. Le club déclaré ne certifie pas l’expéditeur. L’aperçu ne crée aucun relevé. La confirmation vérifie le manager, le club et la révision. Le carnet conserve les champs normalisés du rapport, sans le message, ses en-têtes ni les pièces jointes.

Un import de même contenu normalisé pour le même club conserve un seul relevé. Une variante du mail ou un rapport API de la même période reste consultable séparément. Les désaccords sur les valeurs communes sont calculés à la lecture sur l’ensemble des rapports de la période, y compris hors de la page courante. Pour chaque joueur et chaque phase, la comparaison regroupe les hausses de niveau indiquées sur le joueur ou sur ses séances. Les observations conservées gardent leurs valeurs d’origine lorsqu’une lecture ultérieure fournit une métadonnée facultative. Le bilan utilise le seul rapport sélectionné.

Pour une phase, le bilan CSR additionne les différences signées des joueurs dont les deux valeurs sont connues et indique la couverture. Le total continu exige, par joueur, les deux lignes de phase, les quatre valeurs de CSR et l’égalité entre la fin du collectif et le début de l’individuel. Les ruptures connues sont signalées. Le dénominateur du total continu est l’union des joueurs indiqués, avec une couverture partielle si la liste d’une phase manque. Pour les séances individuelles, la couverture indique combien d’entrées de compétence renseignent le nombre de séances.

Un champ absent ou nul indique une information inconnue. Une liste vide conserve l’absence explicitement signalée. Les rapports peuvent indiquer une progression sans passage de niveau. Les codes de compétence reconnus sont traduits. Les noms et les libellés d’énergie et de niveau sont conservés tels que fournis. Une énergie numérique sans échelle connue est affichée sans unité déduite.

Les consignes prévues, les séances déclarées dans BRT et les résultats rapportés décrivent des observations distinctes. Une variation de CSR ou de compétence ne suffit pas à établir sa cause. Une baisse du CSR seule ne permet pas de conclure à un vieillissement. Les courbes entre relevés complets ont leur propre couverture. Les rapports d’entraînement documentent uniquement les valeurs fournies.

Les statistiques individuelles n’utilisent que des compteurs et dénominateurs connus. La ressource ne fournit ni minutes ni postes : aucun taux par 80 minutes ni ajustement par poste n’est calculé. `balltime` désigne le nombre de portées de balle, pas une durée. L’écran propose les compteurs bruts de carrière ou de championnat pour une saison explicite, leur couverture, le tri et la recherche. La carrière des joueurs actuels peut comprendre d’autres clubs. Le pourcentage de plaquages réussis utilise réussis / (réussis + manqués), seulement si les deux valeurs sont connues et le total positif. Les écarts exigent deux dates ordonnées et un périmètre identique ; une baisse est signalée comme révision du compteur, sans inventer une performance négative.

Les relevés sont privés et inclus dans l’export du manager. L’historique est paginé par vingt observations sans purge automatique. Les lectures de statistiques concernent au plus 200 joueurs, par lots de 50. Les rapports sont bornés à 200 joueurs par phase et dix compétences distinctes par joueur. Une observation normalisée est limitée à 512 000 octets. Les aperçus expirent après dix minutes. La confirmation vérifie la révision, ainsi que les clés pour le parcours API.

## Navigation

La navigation conserve un accès principal au tableau de bord et regroupe les outils : préparation des matchs, développement des joueurs, gestion du club, puis espace personnel et aide. Les groupes peuvent se replier ; un changement de page rend son groupe visible. Les sélections nationales ne voient pas les outils réservés aux clubs. Le menu mobile conserve fermeture, focus clavier et protection des brouillons.

## Validation et publication

L’import et les bilans ont été testés sur des fichiers et des observations synthétiques. Un contrôle privé sur un rapport authentique a confirmé la lecture hors ligne, les valeurs par phase et le parcours de conservation dans l’application locale. La version 2.15.0 a été publiée le 24 novembre 2026 sur [BRT](https://brt.bordebat.fr), après vérification des fichiers servis, des protections d’accès et des sauvegardes. La page publique de connexion a été inspectée dans Chrome. Le CAPTCHA a empêché la recette interactive connectée ; celle-ci et le rendu à largeur étroite restent à vérifier. [Bilan de validation 2.15.0](release-2.15.0-validation.md)
