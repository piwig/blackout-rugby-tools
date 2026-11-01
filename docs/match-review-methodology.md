# Relecture des matchs et import direct

## Objectif

Relier Classic une fois, choisir une rencontre sans télécharger de JSON, puis corriger les événements dont la classification mérite une relecture.

## Conception

Les données importées restent la source. Les corrections sont enregistrées séparément dans l’espace privé du manager. Une empreinte du document et une révision empêchent un onglet ancien d’écraser une correction récente. Un nouvel import conserve les corrections qui correspondent exactement aux mêmes événements ; les autres restent signalées comme non rapprochées.

Une correction distingue attaque, événement hors attaque et événement encore indéterminé. Le côté et la zone restent explicites. Une attaque dont le contexte manque ne contribue pas aux répartitions par zone. Les compteurs distinguent les observations classées, les éléments non classés et les événements hors attaque.

Le manager peut choisir de mémoriser sa correction comme exemple. Des commentaires correspondant à un même modèle de texte peuvent alors recevoir une suggestion privée. Les exemples contradictoires ne produisent pas de suggestion applicable. Le manager valide chaque proposition ; les suggestions ne modifient pas seules les statistiques. Rétablir la source retire la correction et son exemple.

## Import Classic

La liaison par clé manager est conservée et expliquée en étapes courtes. La documentation Classic décrit aussi une connexion par identifiant/mot de passe (`r=lgn`), mais son intégration dépend d’un chiffrement fonctionnel. Aucun mot de passe du jeu n’est demandé par BRT.

L’import direct utilise les identifiants chiffrés déjà enregistrés, un endpoint Classic fixe, une liste bornée de rencontres terminées, puis un aperçu avant confirmation. Un lien officiel sert uniquement à extraire l’identifiant et les indicateurs Club/Juniors/U20/Nationale ; le serveur ne visite jamais une URL saisie. Noms, scores, saison et dates absents restent inconnus.

Les contextes BRT sont `0` pour les clubs seniors, `1` pour les sélections U20, `2` pour les sélections nationales et `3` pour les juniors de club. Le numéro du match et son type forment ensemble son identité, y compris pour les corrections, l’historique, les dossiers adversaires et les exports. Un même numéro peut donc être conservé dans plusieurs contextes sans écrasement. Le filtre de type permet de séparer leurs statistiques.

Le type `3` est interne à BRT : il n’est jamais envoyé comme paramètre `type` à Classic. Les lectures de rencontres (`f`), commentaires (`me`) et scores (`ls`) utilisent `youth=1`. Les noms des clubs (`t`) restent lus dans le contexte club. Pour les rencontres récentes d’un club, le manager choisit explicitement Seniors ou Juniors ; le choix initial reste Seniors. Les sélections U20 et nationales conservent leur contexte propre. Un match en cours ou marqué `data_removed=1` ne produit pas d’import ; une erreur de lecture ne crée aucun match local. Le support documentaire de `me&youth=1` est établi, mais sa réponse complète sur un commentaire junior récent reste à revérifier en conditions réelles. Les tests du dépôt utilisent uniquement des sources synthétiques. Cela n’étend pas les statistiques `fs` aux juniors.

Les imports de fichiers restent disponibles avec aperçu avant confirmation. Un fichier junior doit indiquer `type: 3`, ou être importé avec le choix explicite Juniors. Un drapeau `youth` présent doit être vrai (`true`, `1` ou `"1"`) pour ce contexte et faux (`false`, `0` ou `"0"`) pour les autres. Un conflit avec `type`, `u20` ou `nat` est refusé. Le drapeau seul ne choisit pas silencieusement le contexte. L’export conserve cette information sous la forme canonique `type: 3`. Les clés API, les pièces jointes réelles et les journaux privés ne font pas partie du dépôt public.

## Validation

Tests synthétiques des corrections, conflits, réimports, suggestions contradictoires, isolement des managers, contexte absent, liens invalides et échecs Classic. Vérifications du parcours d’import et de relecture sur écran large et mobile avant publication.

Source technique : [documentation officielle de l’API Classic](https://www.blackoutrugby.com/game/help.documentation.php?category=35&question=329), sections Login, Fixtures et Match Commentary, consultée le 31 octobre 2026.

Contrat junior vérifié dans la documentation officielle le 1er novembre 2026 : [Fixtures (§351)](https://www.blackoutrugby.com/game/help.documentation.php#category=35&question=351), [Match Commentary (§390)](https://www.blackoutrugby.com/game/help.documentation.php#category=35&question=390) et [Live Score (§399)](https://www.blackoutrugby.com/game/help.documentation.php#category=35&question=399).
