# Staff & tactique — méthode coach-lab-v1

Cet atelier est une préparation locale, privée et explicable. Il n’envoie rien dans Classic. Ses indices, références de normalisation et propositions tactiques sont des hypothèses BRT ; aucune formule officielle ni probabilité de victoire n’est revendiquée.

## Parcours

1. Choisir la cohorte, la méthode de sélection, l’objectif et le format d’énergie. Les coefficients et contraintes avancés restent repliés.
2. Calculer le XV, consulter chaque composante puis corriger les maillots 1–23 et les responsables si nécessaire.
3. Déclarer les conditions et éventuellement une observation adverse datée ; comparer trois variantes et ajuster les valeurs numériques.
4. Préparer la feuille corrigée, puis enregistrer seulement ou enregistrer et appliquer au XV local. L’application junior utilise une feuille indépendante.

## Compétences et attributs

Chaque maillot 1–15, capitaine et buteur possède 17 poids indépendants, compris entre 0 et 10 : dix compétences, taille, poids, forme, tempérament (`aggression` de la source), discipline, leadership et expérience. Au moins un poids est positif par rôle. Les dimensions physiques et mentales sont neutres par défaut pour les maillots. Capitaine : leadership 4, expérience 2, discipline 1 ; buteur : pied 4, forme 1.

Pour chaque valeur connue, le score normalisé vaut `100 × clamp((valeur−minimum)/(maximum−minimum),0,1)`, inversé si une valeur faible est favorable. La moyenne utilise les poids positifs. Un attribut requis inconnu rend le score incomplet ; zéro est une valeur connue. Aucune compétence junior masquée n’est reconstruite.

Références initiales éditables : compétences et expérience 0–21 ; forme 0–11 ; taille 150–220 cm ; poids 60–150 kg ; tempérament, discipline et leadership 0–5. Le tempérament privilégie une valeur faible ; les autres une valeur élevée. Ces références sont des hypothèses de travail à vérifier avec l’échelle de la source, pas des plafonds officiels du jeu. Une valeur hors référence est plafonnée, et sa valeur originale reste visible.

Énergie : format déclaré pourcentage 0–110 ou niveau entier 1–11 converti par multiplication par 10. Les valeurs inférieures au seuil excluent le joueur ; énergie inconnue et disponibilité médicale inconnue restent signalées. Une blessure confirmée exclut toujours. La pénalité optionnelle soustrait `abs(score) × pénalité/100 × (110−énergie)/110`. Avec pénalité positive, une énergie inconnue rend le score incomplet. Aucun bonus d’objectif ne modifie silencieusement les indices sportifs ; l’objectif agit sur l’intensité tactique.

## Performances et affectation

La fenêtre couvre quatre mois calendaires jusqu’au jour de génération (borne de départ ramenée au dernier jour du mois si nécessaire). Équipe, cohorte, échelle, poste et nature du poste doivent correspondre exactement. Les postes exacts utilisent les chaînes `1` à `15` et uniquement `observed`. Les rôles larges utilisent les neuf noms de rôles BRT ; `observed` et `report_start` restent séparés. Un pilier au coup d’envoi ne prouve pas le maillot 1 plutôt que 3. Les minutes d’un match ne prouvent pas les minutes à un poste et ne pondèrent donc pas les moyennes.

Moyenne et meilleure performance utilisent les notes connues dans une seule échelle, y compris lorsque ses bornes sont inconnues. Le minimum de notes est configurable ; moins de cinq notes est signalé. Le mélange utilise la moyenne normalisée sur les bornes explicites de l’échelle et la part de compétences déclarée. Même avec une part 0 ou 100, il exige deux indices complets : utiliser la méthode pure correspondante pour éviter cette exigence. Les échelles Classic à bornes inconnues ne sont jamais normalisées implicitement.

L’algorithme hongrois maximise d’abord le nombre de postes calculables puis la somme des scores ; aucun joueur n’est affecté deux fois. Verrouillages, exclusions, blessures et seuil d’énergie s’appliquent. Un verrouillage conserve une décision explicite même si son score est incomplet. Les remplaçants sont proposés ensuite par rôle, jusqu’à huit. Leur couverture signifie qu’un score de compétences complet peut être calculé pour ce rôle, sans garantie officielle d’aptitude. Les responsables sont proposés parmi les titulaires ; les secours parmi les joueurs de la feuille disposant d’un indice complet. Une correction manuelle peut conserver un score incomplet, qui reste affiché ; elle ne contourne pas blessures, exclusions, énergie connue trop faible ou unicité.

## Tactiques

La proposition utilise les moyennes normalisées connues du XV retenu. Une moyenne entièrement inconnue prend un repère neutre 50 uniquement pour les tactiques ; chaque attribut non connu pour les quinze titulaires est signalé. Les quatre priorités d’attaque initiales sont `10 + force`, `10 + technique`, `10 + moyenne(vitesse,dextérité)` et `10 + moyenne(agilité,attaque)`, puis sont réparties en pourcentages entiers totalisant 100 par la méthode des plus grands restes. Sous la pluie, les priorités créative et large sont multipliées par 0,7 et 0,8.

La fréquence de pied est limitée à 10–55 % : `20 + (pied−50)/5 + 10 si pluie − 10 si vent fort`. Les types de pied totalisent 100 ; vent fort favorise touche et réduit chandelle. La défense proposée est glissée si vitesse ≥ force, sinon individuelle. Intensité : équilibré 65, récupération 40, développement 50 ; moyenne d’énergie connue sous 75 réduit de 15, minimum 30. La discipline devient prudente sous la pluie ou sous 50 de discipline normalisée. Ce sont des règles heuristiques documentées, pas un solveur du moteur de match.

Une faiblesse adverse déclarée avec nom, date et source augmente de 10 % la priorité de l’attaque choisie avant répartition ; aucun CSR, score isolé ou résultat ne crée cette information automatiquement. Sans observation, la proposition porte la mention « plan de base ». La variante prudente réduit l’intensité et augmente la fréquence de pied ; la variante possession augmente le pick and go et réduit le pied. La feuille conserve les conditions, observations, références, raisons, inconnues et réglages manuels. Toutes les attaques et tous les types de pied doivent chacun totaliser 100 % avant confirmation.

## Persistance et concurrence

`coach_lab:<équipe>:<cohorte>` conserve le document courant, ses critères et la feuille avec ses preuves. Les notes sources, leurs dates et leur révision sont conservées dans la feuille. `coach_lineup:<équipe>:youth` stocke le XV junior appliqué ; seniors et sélections utilisent le XV historique `lineup:<équipe>`. L’atelier ne change aucune fonction historique ni aucun worker.

Les aperçus `coach_preview:*` sont temporaires, exclus des exports, limités à vingt par compte et expirent après quinze minutes. La confirmation réserve le verrou SQLite puis compare la révision du document, l’empreinte complète de l’effectif et de sa source, celle du XV existant et la révision des performances. Le jeton est lié à la session, à l’équipe et à la cohorte puis consommé une seule fois. Les écritures de feuille et de XV local sont atomiques. Le stockage privé du compte, l’authentification et le CSRF sont ceux de l’application.

L’interface protège les modifications non enregistrées, demande avant de changer de cohorte ou de recharger, et ignore toute réponse devenue obsolète après changement de session, équipe ou cohorte. Les données privées précédentes sont masquées dès le premier rendu d’un nouveau contexte.
