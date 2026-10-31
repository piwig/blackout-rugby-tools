# Relecture des matchs et import direct

## Objectif

Relier Classic une fois, choisir une rencontre sans télécharger de JSON, puis corriger les événements dont la classification mérite une relecture.

## Conception

Les données importées restent la source. Les corrections sont enregistrées séparément dans l’espace privé du manager. Une empreinte du document et une révision empêchent un onglet ancien d’écraser une correction récente. Un nouvel import conserve les corrections qui correspondent exactement aux mêmes événements ; les autres restent signalées comme non rapprochées.

Une correction distingue attaque, événement hors attaque et événement encore indéterminé. Le côté et la zone restent explicites. Une attaque dont le contexte manque ne contribue pas aux répartitions par zone. Les compteurs distinguent les observations classées, les éléments non classés et les événements hors attaque.

Le manager peut choisir de mémoriser sa correction comme exemple. Des commentaires correspondant à un même modèle de texte peuvent alors recevoir une suggestion privée. Les exemples contradictoires ne produisent pas de suggestion applicable. Le manager valide chaque proposition ; les suggestions ne modifient pas seules les statistiques. Rétablir la source retire la correction et son exemple.

## Import Classic

La liaison par clé manager est conservée et expliquée en étapes courtes. La documentation Classic décrit aussi une connexion par identifiant/mot de passe (`r=lgn`), mais son intégration dépend d’un chiffrement fonctionnel. Aucun mot de passe du jeu n’est demandé par BRT.

L’import direct utilise les identifiants chiffrés déjà enregistrés, un endpoint Classic fixe, une liste bornée de rencontres terminées, puis un aperçu avant confirmation. Un lien officiel sert uniquement à extraire l’identifiant et les indicateurs Club/U20/Nationale ; le serveur ne visite jamais une URL saisie. Noms, scores, saison et dates absents restent inconnus.

Les imports de fichiers restent disponibles. Les clés API, les pièces jointes réelles et les journaux privés ne font pas partie du dépôt public.

## Validation

Tests synthétiques des corrections, conflits, réimports, suggestions contradictoires, isolement des managers, contexte absent, liens invalides et échecs Classic. Vérifications du parcours d’import et de relecture sur écran large et mobile avant publication.

Source technique : [documentation officielle de l’API Classic](https://www.blackoutrugby.com/game/help.documentation.php?category=35&question=329), sections Login, Fixtures et Match Commentary, consultée le 31 octobre 2026.
