# Validation des statistiques — 31 octobre 2026

Les contrôles de ce lot vérifient les calculs de BRT à partir de données synthétiques et d’exemples calculés indépendamment. Ils ont permis de corriger plusieurs cas où une donnée partielle, une date ambiguë ou un arrondi pouvait modifier le résultat présenté. Ils ne certifient pas l’exactitude de toutes les données importées ni celle du moteur de jeu Classic.

## Ce qui a été vérifié

- **Matchs et historique** : orientation domicile/extérieur des quatre zones relatives, sommes des attaques, couverture, scores nuls, victoires/nuls/défaites, filtres de type et de saison, agrégats indépendants de la pagination, corrections et réimports.
- **Progression et académie** : moyennes sur les valeurs connues, changements d’effectif et de couverture, valeurs absentes, dévoilements, observations contradictoires au même instant, dates équivalentes en UTC et dates connues seulement au jour près.
- **Composition et indices** : moyennes pondérées par rôle, compétences requises inconnues, seuils d’énergie et de disponibilité, bonus locaux et comparaison de scénarios. Des petites affectations ont été énumérées indépendamment pour vérifier le choix global du XV.
- **Statistiques individuelles Classic** : dénominateurs connus, zéro réel, compteurs manquants ou révisés, périodes carrière/championnat et conservation de relevés successifs. Un exemple de référence donne 80 % de réussite pour 8 plaquages réussis et 2 manqués ; sans total connu et positif, aucun taux n’est produit.
- **Simulations** : conservation de la capacité entière du stade, séances futures de l’académie, plafonnement local et calcul des séances restant avant une cible, sans réutiliser un affichage arrondi.

Les contrôles comprennent des exemples manuels, des invariants de sommes, des permutations d’observations et des oracles utilisant une arithmétique décimale ou entière indépendante. Pour la progression, ils couvrent notamment les changements de joueurs connus et les imports dans un ordre différent. Pour la projection, ils comparent la même quantité de séances répartie sur plusieurs saisons. Les tests de non-régression des défauts corrigés ont d’abord reproduit les résultats erronés, puis vérifié leur correction.

La version 2.8.1 passe **906 tests Python et 89 tests Node**, ainsi que la compilation TypeScript et le build de production. Les tests publics sont dans `tests/` et `web/tests/`. Les vérifications indépendantes complètent ces tests ; leur nombre ne transforme pas cet audit en preuve exhaustive.

## Corrections apportées

| Cas | Résultat corrigé |
| --- | --- |
| Commentaires XML avec contexte partiel | Un événement sans côté ou zone reste dans le total. Une attaque exploitable et un événement inconnu donnent 50 % de couverture, pas 100 %. Les nœuds de texte d’un événement ne sont pas comptés une seconde fois. |
| Scores booléens | `true` et `false` sont refusés comme scores, avant leur conversion possible en 1 et 0. Les scores numériques, y compris zéro et les chaînes numériques Classic, restent acceptés. |
| Gains ambigus à l’académie | Une présence contradictoire au même instant ou deux relevés dont l’ordre est incertain dans la journée ne produisent pas un gain numérique. Une compétence invalide reste inconnue, y compris pour l’écart à un objectif. |
| Moyennes de pourcentages | Les ratios gardent leur précision jusqu’à la moyenne finale. Les parts 1/6 et 1/2 donnent une moyenne de 33,33 %, et non 33,34 %. La moyenne reste calculée par match, sans pondération par son volume d’actions. |
| Répartition du stade | La capacité totale est arrondie une fois, puis les places restantes sont affectées aux plus grands restes. Neuf places restent neuf places après répartition entre les cinq tribunes. |
| Projection de l’académie | Les séances s’accumulent depuis l’observation initiale. Quatre séances à +0,004 ajoutent 0,016, quelle que soit leur répartition entre saisons. Sans séance, une observation de 10,125 reste 10,125. |
| Précision affichée | Les tableaux concernés conservent jusqu’à quatre décimales pour rendre visibles les petits écarts. L’arrondi d’affichage ne remplace pas la valeur utilisée dans le calcul. |
| Fatigue et échelles d’énergie | En mode niveau, seules les valeurs entières de 1 à 11 sont connues. Un niveau 5,5 reste inconnu et ne provoque plus une alerte de fatigue ; un pourcentage décimal reste valide en mode pourcentage. |

Le simulateur visible du stade et le serveur partagent le même résultat d’arrondi décimal : 25 membres × 5,1 donnent 128 places, puis une répartition entière dont la somme vaut 128. Une cible d’académie exigeant plus de séances qu’un entier JavaScript fiable peut représenter est signalée hors limite, sans afficher un compte infini.

La couverture des commentaires vaut **attaques classées / tous les événements**. Les répartitions d’attaques utilisent leurs propres dénominateurs : les attaques classées du côté ou de la zone indiqué. Un événement non classé, un événement hors attaque et une attaque sans contexte complet ne sont pas interchangeables. Une suggestion de classement non validée ne modifie pas les comptes.

## Ce que ces contrôles ne prouvent pas

Une mesure inconnue n’est jamais la preuve d’une valeur nulle. Le dévoilement d’une compétence ne mesure pas sa progression. Une variation observée ne prouve pas sa cause ; une hausse après un entraînement ne permet pas, à elle seule, d’attribuer cette hausse à la séance. Les relevés doivent garder leur date, leur source, leur périmètre et leur couverture.

Le **CSR estimé interne**, les affinités de rôle, les bonus de sélection, les seuils de prudence et les ratios du stade sont des calculs locaux. Ils ne sont ni une formule officielle de CSR, ni des probabilités de victoire, ni une prévision d’affluence. Le CSR observé de Classic reste distinct de l’estimation interne. La projection de l’académie repose sur une hypothèse de gain ; elle ne prédit pas l’IGT, la sortie de l’académie ou une progression officielle.

Les heuristiques de classement des commentaires restent des estimations textuelles. Leurs tests vérifient leur comportement et les comptes qui en découlent, sans certifier qu’elles reconnaissent toutes les actions du jeu.

Les événements XML déjà omis d’un ancien import ne peuvent pas être reconstitués depuis la source normalisée conservée : il faut réimporter le document d’origine ou relire le match. De même, un ancien score booléen déjà converti en 0 ou 1 n’est plus distinguable d’un vrai score sans sa source. Aucune réparation fondée sur une supposition n’est appliquée à ces données.

La comparaison des statistiques individuelles utilise les observations de la page d’historique chargée. Les autres pages restent consultables ; une comparaison entre pages n’est pas proposée dans ce lot.

## Sources et portée de la validation

La [documentation officielle de l’API Classic](https://www.blackoutrugby.com/game/help.documentation.php?category=35&question=329) sert de référence aux ressources de matchs, aux statistiques individuelles et aux rapports d’entraînement. Son champ `balltime` désigne un nombre de portées de balle, pas un temps de jeu ; aucun taux par 80 minutes n’en est déduit.

Les ressources d’instructions et de statistiques individuelles ont déjà été confrontées à des réponses réelles. Au 31 octobre 2026, les tentatives de lecture réelle des rapports d’entraînement `tr` restent refusées par Classic. Leur parseur est testé sur des données synthétiques ; le parcours complet avec un rapport réel réussi reste donc à confirmer. Un refus n’est pas interprété comme une absence d’entraînement ou de progrès.

Ce bilan décrit les calculs et les cas contrôlés, sans annoncer une certification exhaustive ni une validation complète en production. Les exemples publics ne contiennent aucune donnée de manager, aucun secret et aucune pièce jointe privée.

Méthodes détaillées : [optimisation et progression](optimization-methodology.md), [relecture des matchs](match-review-methodology.md), [critères et rapports Classic](community-coaching-methodology.md) et [atelier](workbench-methodology.md).
