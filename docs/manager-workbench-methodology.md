# Vivier, performances et imports explicites

## Vivier privé

Le vivier lit le dernier effectif enregistré de chaque équipe et cohorte dans la base du manager connecté. Le même identifiant joueur peut apparaître dans plusieurs équipes : les sources restent séparées, avec première observation, dernière lecture identique réussie et date d’import. Les différences de valeur sont signalées ; elles peuvent refléter des dates différentes, pas nécessairement une erreur.

Les filtres doivent correspondre à une même observation. Ils ne construisent pas un profil artificiel à partir de l’âge d’une source et des compétences d’une autre. La disponibilité décrit le relevé à sa date. L’âge, la nationalité et une affinité de poste ne garantissent ni disponibilité actuelle ni éligibilité internationale. Les sélections suspendues restent des archives.

Le suivi et les notes du vivier sont propres au manager, distincts des notes de ses clubs. Une révision empêche l’écrasement d’une modification faite dans un autre onglet. La lecture est bornée à 256 contextes et 16 000 observations, avec pagination ; un dépassement est refusé explicitement.

## Performances observées

La lecture directe utilise les ressources officielles Classic `f` (rencontre), `rs` (rapport du reporter) et, pour les seniors de club, `fs` (statistiques de rencontre). La rencontre doit être terminée, correctement datée et concerner l’équipe et le contexte demandés. Le serveur utilise un domaine fixe en HTTPS et ne réalise que des lectures. La source primaire est la [documentation de l’API Classic](https://www.blackoutrugby.com/game/help.documentation.php?category=35&question=329), sections Fixture Statistics et Reporter's Summary.

Le rapport indique une position dans la composition de départ. Cette position n’est pas un historique de tous les rôles joués. Une place sur le banc ne révèle pas le poste effectivement occupé après l’entrée. Les minutes renseignées par `fs` sont les minutes totales du joueur dans le match ; elles ne sont pas attribuées à un rôle après repositionnement. Pour juniors, U20 et NT, les notes `rs` sont lisibles mais les minutes restent inconnues tant que les sélecteurs de contexte de `fs` ne sont pas établis. Une statistique facultative absente conserve les notes disponibles avec un avertissement.

Chaque comparaison sépare équipe, contexte, joueur, position, origine de la position et échelle de notes. Les notes actuelles et historiques Classic sont séparées ; aucune borne de leur échelle n’est inventée. Les compétences actuelles sont un indice distinct, affiché seulement lorsque l’équipe, la cohorte et le rôle correspondent aux données disponibles.

La moyenne arithmétique utilise seulement les notes connues. Exemple : 6, 8 et une note inconnue donnent une moyenne de 7 sur deux notes, minimum 6 et maximum 8. Des minutes 60, inconnues et 20 donnent 80 minutes connues sur deux observations, sans prétendre au total réel des trois matchs. Une valeur zéro renseignée reste zéro. Moins de cinq notes est signalé comme petit échantillon ; ce seuil est un repère de lecture, pas une garantie de fiabilité au-delà. Les adversaires, compétitions, lieux et dates peuvent filtrer l’échantillon, sans correction causale inventée.

La clé de dédoublonnage inclut équipe, contexte, match, joueur, position, origine de la position et échelle. Un doublon identique ne crée pas une seconde performance. Une observation différente exige un remplacement explicite. Le changement d’identité demande suppression de l’ancienne observation puis import de la nouvelle.

### Import et correction manuels

Télécharger le modèle CSV depuis la rubrique, remplacer la ligne fictive, puis relire l’aperçu. Un export JSON produit une liste réimportable. Le champ `context` vaut `club`, `youth`, `u20` ou `nt` ; les identifiants d’équipes restent distincts (`123`, `u20:123`, `nt:123`). Les dates suivent `AAAA-MM-JJ`. Les champs `rating` et `minutes` peuvent être absents en JSON ou vides en CSV. Les bornes d’échelle doivent être cohérentes et peuvent rester toutes deux inconnues lorsque leur source ne les définit pas. `position_basis` distingue une position observée, une position de départ au rapport et un poste de remplaçant inconnu.

Le modèle téléchargé constitue la référence des colonnes acceptées. Limites : 500 lignes par import, 1 Mo de texte, 5 000 observations conservées. L’aperçu dure quinze minutes. Toute modification concurrente de la bibliothèque impose une nouvelle lecture avant confirmation. Les comptes, données et aperçus restent privés ; les exports complets n’incluent que le travail confirmé, jamais les jetons d’aperçu ni les clés API.

## Aperçu d’effectifs

Le nouveau parcours accepte les effectifs CSV/JSON et les feuilles ODS reconnues `players`, `latouff_players`, `moeskroen_ya`, `latouff_academy`. Les autres feuilles et les annexes sont annoncées comme exclues ; les macros et formules ne sont jamais exécutées. Le parcours historique avancé demeure disponible pour les anciens plannings compatibles.

Chaque jeu de données exige une destination explicite ou une exclusion. Deux feuilles ne peuvent remplacer le même effectif dans un lot. L’aperçu affiche les effectifs cibles actuels et les dates. Une date fournie valide ne peut être remplacée par une date plus récente ; une date sans heure doit être complétée sans changer son jour. Un horodatage fourni invalide, futur ou dépourvu de fuseau est refusé. Si la source ne donne aucune date, l’utilisateur renseigne la date réelle du relevé.

Un import différent plus ancien que l’effectif actuel est refusé, tandis qu’un relevé ancien identique ne rafraîchit pas artificiellement les données. Les sélections doivent être rattachées et actives ; le mandat Classic est recontrôlé avant confirmation. Le lot vérifie les droits, toutes les destinations et leurs révisions avant la première écriture, dans une transaction unique. Un échec ne laisse aucun import partiel.

Le parcours historique applique aussi cette protection aux effectifs de clubs, y compris aux feuilles seniors et juniors d’un même classeur. Un refus conserve tous les effectifs, métadonnées et plannings précédents. Les dates JSON `observed_at` ou `date_maj`, la date du classeur et la date de jeu sont respectées ; une date seule conserve sa précision au jour. Les instants invalides, futurs ou sans fuseau et les dates de jeu invalides sont refusés. Pour les fichiers réellement non datés, ce parcours conserve par compatibilité l’heure d’import : elle ne certifie pas l’âge des mesures. Utiliser l’aperçu pour renseigner leur date réelle. Une relecture identique récente actualise la provenance sans créer de point ni de gain de progression.
