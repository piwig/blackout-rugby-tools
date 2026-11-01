# Registre des transferts réalisés — méthode BRT 2.11

Le registre conserve des achats et ventes déjà terminés dans la monnaie virtuelle du jeu. Il est privé à chaque manager et chaque club. Les sélections U20 et nationales sont exclues. Aucun ordre Classic, achat réel, mise à jour de la trésorerie courante ou transformation automatique d’un candidat mercato n’est effectué.

## Données et provenance

Chaque opération possède un identifiant stable unique dans son club, un identifiant et nom de joueur, un type `buy`/`sell`, un instant ISO avec fuseau, une saison déclarée, un montant brut et des frais explicites, une source, ainsi qu’une contrepartie et des notes facultatives. Un montant vide est invalide ; `0` signifie zéro connu. Les dates futures et les dates sans fuseau sont rejetées. Les instants sont normalisés en UTC à la seconde. La saisie manuelle affiche le fuseau local du navigateur, les filtres de période portent sur les jours UTC inclusifs. La saison n’est jamais déduite de la date.

Les montants sont décimaux, finis, positifs ou nuls, au plus `1 000 000 000 000`, avec au plus deux décimales utiles. Les calculs utilisent `Decimal` ; les réponses et exports exposent des chaînes à deux décimales. Les moyennes sont arrondies au centième, demi au supérieur (`ROUND_HALF_UP`). Les affichages localisés ne servent jamais aux calculs.

## Bilans

Les filtres saison, période et joueur sont appliqués avant les statistiques, les regroupements et la pagination. La recherche porte sur le nom ou l’identifiant exact du joueur. Les opérations annulées restent visibles et comptées à part, et sont exclues de tous les agrégats financiers et records.

- Achats bruts = somme des montants des achats actifs ; ventes brutes = somme des montants des ventes actives.
- Tous les frais = frais des achats et des ventes actifs.
- Balance nette = ventes brutes − achats bruts − tous les frais.
- Achats/ventes moyens bruts = montant brut total du type / nombre d’opérations actives de ce type. Une moyenne sans observation est inconnue, affichée `—`.
- Plus gros achat et plus grosse vente bruts = maximum du montant brut du type. Plus grosse vente nette = maximum de `montant de vente − frais de cette vente`. Une vente nette peut être négative si ses frais dépassent son prix. Les égalités sont départagées de façon déterministe par identifiant.
- Le bilan par joueur regroupe les flux par identifiant, même si le nom a changé ; le nom de l’opération la plus récente dans le périmètre filtré sert de libellé (instant UTC, puis identifiant en cas d’égalité). Il ne prétend pas mesurer un bénéfice incluant les salaires. Plusieurs cycles achat/vente, ventes sans achat connu ou achats encore détenus ne sont jamais appariés artificiellement.

Le résumé de l’aperçu est le bilan projeté du registre entier après dédoublonnage et application des corrections proposées. La liste de l’aperçu présente les lignes entrantes normalisées et leurs détails, y compris les lignes qui seront ignorées comme doublons.

## Versions et imports

Une correction conserve l’identifiant et exige un motif. Une annulation conserve toutes les données et exige un motif ; une restauration exige aussi un motif. Chaque action produit un instant et une photographie complète supplémentaire dans `versions`. La saisie manuelle ne permet pas de changer le statut au moyen d’une simple correction. Il n’existe pas de suppression destructive.

L’import accepte CSV UTF-8 (BOM accepté, en-têtes nommés, guillemets et retours à la ligne correctement échappés) ou JSON. Le JSON peut être une liste ou `{ "schema": "brt-transfer-ledger-v1", "entries": [...] }`. Le modèle téléchargeable contient un exemple explicitement fictif à remplacer. Les champs supplémentaires, les champs requis manquants, les nombres/date invalides et les collisions contradictoires au sein d’un fichier invalident tout l’import. Les identifiants identiques au contenu identique sont ignorés sans nouvelle version. Un identifiant existant dont le contenu diffère exige le mode de correction explicite et son motif. Ce mode permet également d’importer une correction de statut, avec le motif de correction et le motif d’annulation dans la photographie correspondante.

Un aperçu est lié au manager, à la session authentifiée, au club, à l’état de la fiche club et à la révision courante du registre. Il expire après quinze minutes. Toute modification de contenu, format, mode ou motif côté interface invalide l’aperçu affiché. Sa confirmation revérifie les liens, la présence du club et la révision sous `BEGIN IMMEDIATE`, puis écrit le lot et consomme le jeton dans la même transaction. Une erreur ne confirme aucune ligne. Les aperçus temporaires `transfer_preview:*` doivent être exclus de l’export global. Les documents durables sont `transfer_ledger:<club>`.

L’export CSV/JSON est intégral pour le club, indépendamment des filtres, et conserve identifiants, données courantes, statut et motif d’annulation. Le réimport identique, y compris un export vide, est sans effet. Cet échange portable décrit l’état courant ; il n’importe pas des dates d’audit comme des événements locaux prétendument survenus. L’export global privé du manager conserve le document durable complet et son journal de versions. Dans un autre club, l’import portable crée de nouvelles premières versions locales.

Limites : 1 000 opérations par club/fichier, contenu importé de 4 000 000 octets maximum, cinq aperçus privés temporaires, 100 versions par opération, document durable de 16 000 000 octets maximum, 100 résultats maximum par page (50 par défaut). Les textes ont des longueurs bornées. Aucun espace de compte ni secret ne figure dans les exemples ou tests.

À chaque aperçu puis à chaque persistance (saisie, correction, annulation, restauration, confirmation), le serveur produit les deux exports portables proposés et mesure leurs octets UTF-8. Chacun doit rester au plus à 4 000 000 octets, et son enveloppe JSON de réimport doit rester sous la limite HTTP globale de 8 200 000 octets. Le contrôle de l’enveloppe réserve la longueur maximale du club, de la révision et d’un motif de correction avec échappement maximal. Les notes Unicode, guillemets, retours à la ligne et caractères de contrôle sont donc comptés selon leur encodage réel, pas leur nombre de caractères. Un lot individuellement admissible peut être refusé si le registre cumulé dépasserait cette capacité. Le refus est atomique : aucune opération, révision, version ou consommation de jeton n’est enregistrée. L’interface explique la limite ; réduire les notes dans une correction permet de libérer de la capacité portable tout en conservant leurs anciennes versions dans l’audit durable. Aucun export n’est tronqué.

## Intégration et vérification

`register_transfer_ledger(app, store, auth, require_team)` enregistre les routes privées `/api/transfer-ledger`, `/cancel`, `/restore`, `/preview`, `/confirm`, `/template` et `/export`. `TransferLedger(Actions)` occupe l’onglet « Transferts réalisés » ; son panneau interne est ouvert par défaut. Sa clé réinitialise le contexte à chaque changement de club, utilisateur ou session ; ses requêtes tardives sont ignorées après démontage ou relance StrictMode. Les filtres facultatifs vides sont omis de la requête ; une période peut n’avoir qu’une borne. Le brouillon garde la révision capturée à son ouverture, même après lecture d’une autre page de résultats. Le garde de navigation protège saisie, import et requêtes en cours.

Les tests dédiés utilisent des clubs et joueurs synthétiques et exercent les routes réelles de l’application : balances, frais, cycles multiples, filtres UTC, moyennes, records, corrections/annulations/restaurations, imports atomiques, doublons/conflits, concurrence, sessions, CSRF, droits club, réimport CSV/JSON et expiration. Les tests Node exécutent le composant transpillé : protection du brouillon, double soumission, réponse tardive, StrictMode, identité club/session, invalidation de l’aperçu et rendu de l’audit. La validation complète de l’intégration et du rendu navigateur appartient au coordinateur.
