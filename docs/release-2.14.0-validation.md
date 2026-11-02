# BRT 2.14.0 — Observations et comparaison récente

## Comportement

Les effectifs seniors et juniors disposent d’une vue essentielle et d’une vue complète. La seconde affiche les caractéristiques observées, les étoiles de recrutement sans plafond artificiel127, les évolutions chiffrées et les notes privées à droite. Une révélation est identifiée distinctement d’un gain. Les champs main/pied et appartenances nationales sont préservés par les nouveaux imports ; ils ne sont pas reconstruits dans les anciens relevés.

Après lecture des feuilles, Jour de match propose les quatre derniers matchs terminés de chaque participant. Scores, météo, poids historiques et notes collectives viennent de Classic. Les rapports absents ou incohérents ne sont pas remplacés par des matchs plus anciens. Un score absent peut être complété via le relevé Classic après confirmation de fin ; aucune note n’est déduite du résultat. Les lectures de reports et scores partagées sont dédupliquées.

Les écrans concernés indiquent la nature de leurs chiffres : observations, mélange d’observations/simulations ou modèles personnels. Les dates d’observation restent distinctes des dates d’import. Ce lot n’est pas une nouvelle validation de toutes les formules des simulateurs existants.

## Contrats

Authentification, CSRF et appartenance à l’espace privé sont requis pour le nouvel endpoint `/api/match-sheet/recent`. Tous les appels Classic sont en lecture seule, avec population explicite seniors/juniors/U20/national et identité contrôlée. Limites : deux historiques de20fixtures, quatre lignes par côté, noms par lots10, huit reports et au plus huit replis de score ; aucun envoi dans le jeu.

Les tests emploient des données synthétiques. La vérification réelle porte sur notre propre club et une rencontre de club, via notre seul accès développeur pour les données publiques. Les sélections réelles d’autres managers ne sont pas utilisées. Aucune donnée de compte ni capture n’est publiée ici.

## Limites explicites

Les étoiles dépendent de la source et des droits/premium Classic. Une ancienne valeur127 n’est jamais remplacée automatiquement par600. La météo reste affichée par son code Classic lorsque le libellé n’a pas été vérifié ; aucune icône de soleil ou pluie n’est inventée. Une note de reporter n’est pas une fréquence tactique, une causalité ou un pronostic, et son échelle maximale n’est pas supposée. Les noms des clubs sont ceux de la lecture actuelle.

Références : [BRM V4](https://brm.webyzo.com/V4/index.php), [documentation API Classic](https://www.blackoutrugby.com/game/help.documentation.php?category=35&question=329), notamment Fixtures, Players et Reporter's Summary. Les captures transmises ont guidé les améliorations d’usage ; aucune parité complète avec BRM n’est revendiquée.

## Validation locale

1 395 tests Python et 232 tests Node réussis ; TypeScript et build vérifiés. Les quatre catalogues contiennent 3 817 clés, sans manque ni paramètre incohérent. Les avertissements existants concernent TestClient et la taille du bundle. Un contrôle local synthétique a vérifié la note junior après enregistrement/rechargement,600étoiles intégrales, une révélation distincte d’un gain, huit cartes récentes avec scores0–0 et l’affichage anglais à390px sans débordement de page.
