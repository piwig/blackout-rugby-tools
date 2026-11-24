# BRT 2.15.0 — Import des rapports d’entraînement Classic

Version locale, non publiée. L’étiquette 2.15.0 figure dans le menu latéral et dans la réponse de `GET /api/health`.

## Parcours

Dans **Progression → Rapports d’entraînement**, un manager connecté à BRT peut choisir un club de son espace privé et joindre le corps HTML d’un rapport Classic en anglais ou un EML qui le contient. L’analyse est limitée à 2 Mio avant et après décodage. Elle fonctionne sans clé Classic et sans appel à Classic. Le traitement ignore les scripts et les ressources distantes du document.

L’aperçu indique la destination, le club déclaré, la période, la provenance et les avertissements. La déclaration du club dans le document ne certifie pas l’expéditeur. Un joueur absent de l’effectif actuel peut figurer dans un rapport ancien. L’aperçu laisse le carnet intact jusqu’à sa confirmation. La confirmation est liée au manager, au club et à la révision, et l’annulation permet de quitter l’aperçu.

Un nouvel import du même contenu normalisé pour ce club est détecté comme doublon. Les variantes et le rapport API de la même période restent sélectionnables séparément. BRT signale à la lecture les désaccords sur les valeurs communes, y compris entre pages d’historique. Les rapports déjà conservés gardent leur contenu d’origine. L’import ne modifie aucun entraînement dans le jeu.

## Lecture des résultats

Le bilan porte sur un rapport à la fois. Chaque phase additionne les écarts de CSR connus. Le total continu exige deux lignes, quatre valeurs connues et un CSR identique au raccord entre le collectif et l’individuel. Sa couverture utilise l’union des joueurs indiqués, avec un avertissement si une liste manque. Les ruptures connues restent visibles.

L’interface distingue les listes absentes des listes explicitement vides. Le détail reprend les séances, les entraîneurs et leurs niveaux, les passages de niveau et l’énergie fournis. BRT traduit les codes de compétence reconnus et affiche les noms et libellés d’origine. Un libellé d’énergie ou de niveau reste textuel. L’absence de passage de niveau peut coexister avec une progression. Une baisse de CSR seule ne permet pas de conclure à un vieillissement. [Méthodologie des rapports](community-coaching-methodology.md)

## Validation locale

Ces résultats ont été relevés avant les corrections de la revue intégrée. La validation finale après ces corrections reste à consigner.

- La suite du backend fonctionnel a donné 1 458 tests Python réussis. Un contrôle de l’application complète sur un stockage temporaire a ensuite confirmé le statut 200 et la version 2.15.0 sur `GET /api/health`.
- La suite frontend a donné 250 tests Node réussis. Les quatre catalogues contiennent chacun 3 881 clés, sans clé manquante, supplémentaire ou invalide. TypeScript et le build de production ont réussi.
- Les avertissements existants concernent l’utilisation de `httpx` avec Starlette TestClient et la taille d’un bloc JavaScript Vite.
- Un contrôle privé sur un rapport authentique a confronté les phases, les passages, les séances et les CSR à des totaux établis indépendamment. Le parcours dans l’application locale a confirmé l’authentification, la protection CSRF, l’absence d’écriture à l’aperçu, la confirmation, la relecture et la détection du doublon sans clé Classic.
- Les réponses réelles de `ti` (instructions) et `ps` (statistiques) avaient été vérifiées auparavant. Pour `tr` (rapports via l’API), la validation repose sur la documentation et les tests synthétiques. Le contrôle privé concerne le parcours par fichier.

Chrome a ouvert l’application locale avec des données synthétiques. La connexion du débogueur est restée indisponible pour l’inspection, les interactions et les captures après une tentative de reprise sur le même onglet. Le parcours interactif connecté et le rendu à largeur étroite restent à vérifier sur navigateur.
