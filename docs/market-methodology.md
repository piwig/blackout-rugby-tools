# Mercato & budget

Le carnet de chaque club prépare les recrutements et investissements à partir de relevés manuels. Il ne lit pas automatiquement le marché et ne transmet aucun achat, aucune vente, aucune enchère ni commande à Classic. Les candidats, notes et budgets restent dans l’espace privé du manager. Les sélections nationales et U20 n’ont pas accès à cette rubrique.

## Relever les moyens disponibles

Le manager indique la trésorerie actuelle, les recettes et dépenses hebdomadaires, la réserve à conserver et les engagements non encore débités. Les dépenses couvrent tous les coûts récurrents actuels. Un coach déjà inclus dans le salaire du staff ne doit pas être ajouté une seconde fois ; une construction déjà payée n’est plus un coût à venir. Une vente espérée, une recette de billetterie incertaine ou une économie de remplacement ne constitue pas une rentrée acquise.

Un champ vide signifie inconnu. Zéro n’est utilisé que s’il a été explicitement saisi. Les montants sont non négatifs, finis et limités à 1 000 milliards d’unités de monnaie du jeu. L’interface accepte les centimes. Le calcul serveur utilise des décimaux avant la conversion en nombres JSON.

Le relevé est daté dans le fuseau local du navigateur, puis conservé avec un fuseau explicite. Le manager confirme qu’il a vérifié la couverture du budget. Une date manquante ou future, un montant absent ou une confirmation non cochée empêche toute conclusion de compatibilité et laisse le plafond inconnu. Une ancienne date reste visible : BRT ne certifie pas la fraîcheur de la saisie ni son exhaustivité.

## Quatre semaines, deux contraintes

En notant `C` la trésorerie, `I` les recettes hebdomadaires, `E` les dépenses hebdomadaires, `R` la réserve et `B` les engagements restant à débiter :

```text
Solde hebdomadaire                     = I − E
Trésorerie projetée à quatre semaines  = C + 4 × (I − E) − B
Marge immédiate                       = C − R − B
Marge projetée après réserve          = C + 4 × (I − E) − B − R
Plafond prudent de dépense initiale    = max(0, min(marge immédiate, marge projetée))
```

Le plafond n’est fourni que pour un budget complet, confirmé et daté. Les marges négatives restent affichées avec leur déficit ; seul le plafond de dépense est borné à zéro. Une rentrée prévue au cours des quatre semaines ne permet donc pas d’augmenter la dépense réalisable immédiatement. Les dates intermédiaires de paiements et les échéanciers contractuels ne sont pas simulés.

Chaque scénario est indépendant. Le carnet n’additionne pas tous les achats ni tous les projets, même s’ils sont marqués « Retenu pour comparaison ».

## Coût d’un candidat

Pour un prix `P`, des frais d’achat `F` et un salaire supplémentaire hebdomadaire `S` :

```text
Décaissement initial                   = P + F
Coût total sur quatre semaines         = P + F + 4 × S
Marge immédiate après achat            = marge immédiate − P − F
Marge projetée après achat             = marge projetée − P − F − 4 × S
Prix maximum du joueur                 = max(0, min(marge immédiate − F,
                                                   marge projetée − F − 4 × S))
```

Le salaire est intégralement additionnel : aucun départ ni allègement de masse salariale n’est supposé. Le prix, les frais et le salaire doivent tous être connus pour conclure. « Compatible avec ce budget confirmé » signifie seulement que les deux marges calculées sont non négatives sous les hypothèses saisies ; ce n’est ni une recommandation sportive, ni une autorisation, ni une prévision officielle. Un candidat écarté reste conservé pour mémoire et son scénario demeure indépendant.

Exemple fictif : avec 1 000 de trésorerie, 200 de recettes hebdomadaires, 100 de dépenses, 100 de réserve et 100 d’engagements, la marge immédiate vaut 800 et la marge projetée 1 200. Le plafond initial est donc 800. Un joueur à 500, avec 20 de frais et 50 de salaire supplémentaire par semaine, coûte 720 sur quatre semaines. Les marges restantes sont 280 aujourd’hui et 480 à quatre semaines ; son prix maximum est 780.

L’identifiant Classic facultatif doit contenir uniquement un entier positif de quinze chiffres au plus. BRT construit le lien officiel `https://www.blackoutrugby.com/game/club.squad.php#player=<identifiant>` ; le carnet n’accepte pas d’URL externe libre. Le lien est un accès au profil, pas un ordre d’achat.

## Comparer le besoin sportif

Les dix compétences observées sont saisissables de 0 à 21. L’âge, facultatif, est conservé sans coefficient de potentiel ni seuil automatique de vente. Le manager peut choisir un senior de référence pour comparer les niveaux connus, compétence par compétence. Un tiret représente une valeur inconnue.

L’indice au rôle utilise les coefficients par défaut de BRT et la méthode `weighted-average-v1`, comme les affinités historiques. Il ne reprend pas les profils personnalisés de l’atelier de composition. Une compétence requise manquante empêche le calcul de l’indice du candidat. Le meilleur indice de l’effectif est calculé uniquement parmi les seniors dont les compétences nécessaires sont connues ; la couverture et la date du relevé restent visibles. Un effectif absent ou incomplet ne devient pas un point de comparaison certain. La différence affichée est celle entre l’indice du candidat et le meilleur indice comparable au même rôle.

Ces indices n’intègrent ni la disponibilité, ni la forme, ni les minutes jouées, ni une future progression. Ils ne mesurent pas la probabilité de victoire. Le CSR seul ne justifie pas un recrutement. Les informations d’un candidat peuvent évoluer sur le marché ; ses notes permettent de conserver la source, le besoin et les points à revérifier.

## Staff et infrastructures

Chaque projet utilise son coût initial restant à payer et son coût hebdomadaire supplémentaire. Le coût total est `coût initial + 4 × coût hebdomadaire`, avec les mêmes contrôles de marge immédiate et projetée. Aucun bénéfice sportif, revenu d’affluence ou rendement financier n’est inventé. Les projets ne sont pas achetés ensemble. Une durée d’engagement supérieure à quatre semaines doit être examinée au-delà de l’horizon affiché ; les notes conservent cet élément sans l’assimiler à une dépense déjà effectuée.

## Conservation et contrôles

« Comparer les scénarios » calcule à partir du brouillon affiché sans le sauvegarder. Une modification du carnet masque les résultats précédents jusqu’au prochain calcul ; un identifiant de relevé d’effectif différent de celui affiché masque la comparaison sportive et le senior de référence. Le bouton « Actualiser l’effectif et recalculer » relit l’état du club puis recalcule sur le brouillon conservé. La source de l’analyse est l’identifiant du relevé réellement utilisé par le serveur, jamais celui supposé par le navigateur. « Enregistrer le carnet » conserve le budget, jusqu’à cinquante candidats et vingt projets, puis renvoie l’analyse correspondante. Aucune sauvegarde automatique ni action de jeu n’a lieu.

Le carnet est isolé par manager et par club, protégé par session, CSRF et révision optimiste. Un conflit entre onglets conserve les saisies et interdit leur écrasement aveugle. La relecture explicite demande confirmation avant d’abandonner un brouillon. Les champs et actions sont bloqués pendant une requête ; les réponses d’un écran quitté sont ignorées. La navigation, le changement de club, la déconnexion et la fermeture de page avertissent en présence d’un brouillon ou d’une opération en cours.

Les documents `market:<team_id>` sont inclus dans l’export JSON privé via `manager_documents`, selon la politique existante de l’application. Les exports restent à protéger comme les autres informations du club.

Les tests couvrent les montants inconnus, zéro explicite, limites numériques, dates, calculs décimaux, deux plafonds, scénarios indépendants, coefficients et couverture, isolation et conflits. Côté interface, les tests ciblent également la répétition d’effets React, les réponses tardives, le verrouillage des doubles sauvegardes et la révision utilisée après enregistrement.
