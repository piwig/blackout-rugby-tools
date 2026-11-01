# Compléter l'atelier du manager — BRT 2.11

## Objectif et choix

L'utilisateur demande de livrer les sept écarts observés dans BRM : XV selon les performances, XV junior, coefficients avancés par maillot, capitaine/buteur, propositions tactiques, économie du stade et historique des transferts. L'exécution, GitHub public et le déploiement VPS sont déjà autorisés. Les choix ci-dessous sont des décisions d'implémentation du coordinateur.

Approche retenue : trois modules privés intégrés au produit existant, avec leurs calculs purs et leurs tests. Étendre les fonctions historiques en place risquerait de modifier silencieusement des scénarios et le pilote Classic ; les nouveaux calculs ont donc une méthode versionnée et un espace explicite. Copier les formules opaques de BRM ne permettrait pas de vérifier leur sens : les propositions BRT expliquent leurs hypothèses.

## Contraintes globales

- Python/FastAPI/SQLite et React/TypeScript existants, sans nouvelle dépendance requise.
- Aucune écriture Classic, aucun changement du worker vacances, aucune action de jeu ou d'argent réel.
- Authentification privée, CSRF, révisions et transactions ; aucun secret ni fait de compte dans Git.
- Clubs, juniors, U20 et NT séparés. Une sélection n'a pas d'académie ni de finances de club.
- Valeurs inconnues et zéro distincts ; pas de formule officielle, de probabilité de victoire ou de rentabilité garantie revendiquée.
- Sources et dates conservées, brouillons protégés, réponses tardives ignorées après changement de compte/équipe, interface responsive et FR/EN/ES/IT.
- Calculs déterministes, bornés et explicables. Les anciennes fonctions gardent leur comportement.

## Staff & tactique

Nouvelle rubrique de préparation regroupant feuille senior/junior ou sélection, critères et responsables, performances et plan de jeu. Chaque contexte possède son document et sa feuille ; un changement de cohorte ne peut écraser l'autre.

Les coefficients couvrent les maillots 1 à 15, capitaine et buteur. Dix compétences, taille, poids, forme, tempérament, discipline, leadership et expérience sont disponibles, avec poids de 0 à 10 et références de normalisation visibles. L'énergie utilise un format explicite, un seuil et une pénalisation réglable. Les valeurs physiques et mentales ne reçoivent aucun poids sportif par défaut hors des responsables. Les références sont des hypothèses BRT éditables, pas des règles du moteur du jeu. Une donnée requise inconnue rend le score incomplet.

Le XV peut être proposé selon les compétences, la moyenne des performances, la meilleure performance, ou un mélange explicite. La période par défaut couvre les quatre derniers mois calendaires. Équipe, cohorte, échelle et nature du poste doivent correspondre ; aucune fusion d'échelles. Les notes ne sont pas pondérées par des minutes attribuées sans preuve au poste. Les petits échantillons sont indiqués et un minimum de notes est réglable. Un mélange nécessite des bornes d'échelle explicites ; les notes Classic à bornes inconnues restent comparables entre elles sans normalisation inventée. Verrouillages, exclusions, blessures, énergie et unicité du joueur s'appliquent ; aucune compétence junior masquée n'est reconstruite.

Capitaine et buteur sont classés avec leurs composantes connues, une proposition parmi les titulaires et des secours. Le banc affiche ses couvertures et lacunes. Une feuille peut être corrigée manuellement avant sauvegarde. L'application locale aux seniors/sélections contrôle aussi le XV historique ; les juniors ont une feuille dédiée. Aucun envoi au jeu.

Le plan tactique propose quatre parts d'attaque totalisant 100 %, une fréquence de pied et ses types totalisant 100 %, défense, discipline et intensité. Il dépend du XV choisi, d'un objectif, des conditions déclarées et d'un profil adverse facultatif daté. Sans adversaire connu, il donne un plan de base signalé comme tel. Une comparaison limitée de variantes expose les raisons et inconnues ; aucun contre certain n'est inféré depuis CSR ou un résultat isolé. La feuille enregistrée conserve ces réglages et leur provenance.

## Économie du stade

Scénarios privés de capacité, tarif, remplissage par catégorie, coût variable par spectateur, recettes annexes, charges fixes par match, entretien hebdomadaire et investissement. Paramètres inconnus vides, source et date explicites. Aucun tarif actuel du jeu n'est inventé. Saisie initiale depuis les capacités du club si disponibles, puis comparaison actuel/projet.

Résultats par match et pour plusieurs taux de remplissage : entrées, recettes, coûts, net ; projection sur un nombre explicite de matchs et semaines, seuil de rentabilité et récupération de l'investissement uniquement quand les données et le gain supplémentaire le permettent. Ne pas mélanger charges hebdomadaires et par match ni traiter une recette prévue comme encaissée. Sauvegarde, duplication, export et relecture des scénarios.

## Registre des transferts

Registre des opérations réalisées, distinct du carnet de candidats. Chaque entrée : identifiant, joueur, achat/vente, date avec fuseau, saison déclarée, montant, frais, contrepartie facultative, source, notes. Montants virtuels seulement. Saisie et import CSV/JSON avec modèle, aperçu et confirmation ; révision, dédoublonnage, correction et annulation traçable. Un achat projeté ne devient jamais un achat réalisé automatiquement.

Bilan par saison, période et joueur : nombres, achats, ventes, frais, balance nette, moyennes et records avec leur définition. Annulations exclues et visibles. Le gain achat/revente ne doit pas prétendre inclure les salaires inconnus. Export réimportable ; archives propres à chaque club. Pas de transmission au jeu.

## Validation et livraison

Tests de calculs indépendants, contraintes du XV, données manquantes, cohortes, échelles, doublons, invalidation des aperçus et isolation des managers. Revues indépendantes des trois modules puis de l'intégration. Parcours Chrome synthétiques desktop/mobile ; tests complets, build, audit des fichiers publics, GitHub, sauvegarde/deploiement puis contrôle HTTPS/API/assets et bases.
