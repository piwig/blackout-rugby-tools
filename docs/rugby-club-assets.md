# Marques des clubs de rugby

Catalogue préparé, téléchargé et inspecté le **30 octobre 2026** pour le choix facultatif du club favori dans l'espace privé BRT. Les huit marques proviennent de sites officiels de clubs ou de la Ligue nationale de rugby. Aucun logo n'a été inventé ou généré.

Le catalogue utilisable par React est `web/src/rugby-clubs.ts` : `rugbyClubs` expose `id`, `name`, `shortName`, `logo` (chemin local) et `source` (page officielle). L'option `none` appartient au profil et n'est pas un club. Les identifiants sont ceux du profil persistant.

## Fichiers livrés

Tous les fichiers publics sont des PNG RGBA transparents, statiques, sans métadonnées du téléchargement. Poids total : **137 127 octets**, soit environ 134 Kio. Les rapports de dimensions et les couleurs des marques sont conservés.

| Identifiant | Fichier public | Dimensions | Octets | Marque / détenteur identifié | Source officielle |
| --- | --- | --- | ---: | --- | --- |
| `toulouse` | `/images/clubs/toulouse.png` | 219 × 256 | 24 851 | Stade Toulousain | [LNR — Stade Toulousain](https://top14.lnr.fr/club/toulouse) |
| `larochelle` | `/images/clubs/larochelle.png` | 199 × 256 | 42 075 | Stade Rochelais | [LNR — Stade Rochelais](https://top14.lnr.fr/club/la-rochelle) |
| `leinster` | `/images/clubs/leinster.png` | 256 × 244 | 5 766 | Leinster Rugby | [Leinster Rugby](https://www.leinsterrugby.ie/) |
| `racing92` | `/images/clubs/racing92.png` | 151 × 151 | 7 584 | Racing 92 | [LNR — Racing 92](https://top14.lnr.fr/club/racing-92) |
| `toulon` | `/images/clubs/toulon.png` | 151 × 151 | 14 702 | RC Toulon | [LNR — RC Toulon](https://top14.lnr.fr/club/toulon) |
| `clermont` | `/images/clubs/clermont.png` | 151 × 151 | 9 575 | ASM Clermont Auvergne | [LNR — ASM Clermont](https://top14.lnr.fr/club/clermont) |
| `munster` | `/images/clubs/munster.png` | 256 × 256 | 14 705 | Munster Rugby | [Munster Rugby — The Munster Crest](https://www.munsterrugby.ie/about-munster-rugby/munster-crest) |
| `crusaders` | `/images/clubs/crusaders.png` | 364 × 130 | 17 869 | Crusaders Rugby | [Crusaders Rugby](https://www.crusaders.co.nz/) |

Les noms ci-dessus identifient les marques sportives et leurs clubs ; ce relevé ne constitue pas une recherche juridique sur le titulaire enregistré de chaque marque. Aucune licence libre ni autorisation générale de réutilisation n'a été constatée. Les marques restent celles de leurs titulaires. Leur choix indique une préférence du manager, sans affiliation, partenariat, soutien ou validation de BRT par les clubs, la LNR ou les compétitions.

Mention courte à afficher avec les sources dans les crédits : « Logos des clubs : marques de leurs titulaires respectifs, issues des sites officiels des clubs et de la LNR. Utilisés pour le choix personnel d'un club favori. Aucune affiliation avec BRT. » Les liens `source` permettent de créditer individuellement les clubs.

## URLs de téléchargement observées

Les cinq URLs LNR sont présentes dans [la liste officielle des clubs du TOP 14](https://top14.lnr.fr/clubs), sous les noms correspondants. Les URLs n'ont pas été déduites de noms de fichiers. Les trois autres sont référencées dans le HTML des sites officiels indiqués.

| Identifiant | Ressource observée | Fichier source | Traitement |
| --- | --- | --- | --- |
| `toulouse` | [PNG LNR](https://cdn.lnr.fr/club/toulouse/photo/logo.7b3a5c7e101ff4bcae0273003948fecd5181e0b5) | 1772 × 2069, 115 937 octets | Réduction proportionnelle Lanczos à 219 × 256 ; réencodage PNG |
| `larochelle` | [PNG LNR](https://cdn.lnr.fr/club/la-rochelle/photo/logo.7b3a5c7e101ff4bcae0273003948fecd5181e0b5) | 2150 × 2764, 101 518 octets | Réduction proportionnelle Lanczos à 199 × 256 ; réencodage PNG |
| `leinster` | [SVG officiel, variante Light](https://d2tqzbbf1n6xva.cloudfront.net/leinster2023/wp-content/uploads/2023/08/31143344/Leinster-Logo-Light.svg) | SVG 108 × 103, 8 873 octets | Rendu du dessin vectoriel en PNG 256 × 244 ; variante blanche intacte |
| `racing92` | [PNG LNR](https://cdn.lnr.fr/club/racing-92/photo/logo.7b3a5c7e101ff4bcae0273003948fecd5181e0b5) | 151 × 151, 7 962 octets | Réencodage PNG à taille identique |
| `toulon` | [PNG LNR](https://cdn.lnr.fr/club/toulon/photo/logo.7b3a5c7e101ff4bcae0273003948fecd5181e0b5) | 151 × 151, 15 364 octets | Réencodage PNG à taille identique |
| `clermont` | [PNG LNR](https://cdn.lnr.fr/club/clermont/photo/logo.7b3a5c7e101ff4bcae0273003948fecd5181e0b5) | 151 × 151, 10 035 octets | Réencodage PNG à taille identique |
| `munster` | [SVG officiel](https://www.munsterrugby.ie/themes/custom/munster/files/Munster.svg) | SVG 600 × 600, 18 717 octets | Rendu du dessin vectoriel en PNG 256 × 256 |
| `crusaders` | [PNG officiel](https://www.crusaders.co.nz/images/site-logo.png) | 364 × 130, 19 044 octets | Réencodage PNG à taille identique |

Les SVG ont été analysés comme XML et contiennent uniquement `svg` et `path`. Aucun script, gestionnaire d'événement, `foreignObject`, image incorporée, référence externe, entité ou DTD n'a été accepté. Ils ont été rasterisés avec `@resvg/resvg-js`, sans charger de police système ; seuls les PNG sont servis. Pillow 12.2.0 a décodé et réencodé les pixels, puis réduit les deux grands PNG. Le convertisseur a été installé dans un dossier temporaire hors dépôt ; aucune dépendance de l'application n'a été ajoutée.

## Affichage et contrôles

- Utiliser `object-fit: contain`, sans étirement, recadrage ou masque qui coupe les marques.
- Prévoir une surface sombre, par exemple `#183246` : Leinster est la variante blanche officielle et Racing 92 / Crusaders comportent du texte blanc. Ne pas les poser directement sur du blanc. Les huit marques ont été inspectées ensemble sur cette surface.
- Le logo Crusaders est horizontal : conserver sa signature complète. Les fichiers Racing 92, Toulon et Clermont sont des sources 151 × 151 ; ils conviennent aux sélecteurs et avatars, pas à de grandes bannières haute résolution.
- Prévoir le nom du club comme texte accessible et un état « Aucun club favori ». Le choix n'a aucune incidence sur le compte Classic ni sur les données des équipes.
- Huit fichiers décodés et vérifiés, dimensions bornées à 364 px, PNG statiques non vides, alpha présent. Pas de SVG public ni de chargement de logo distant à l'exécution.
- L'inspection visuelle couvre Toulouse (monogramme rouge/noir), La Rochelle (navire jaune), Leinster (harpe blanche), Racing 92 (écusson ciel et blanc), Toulon (muguet et trois étoiles), Clermont (écusson ASM), Munster (cerf et couronnes), Crusaders (symbole rouge/noir et signature).

## Empreintes SHA-256 des fichiers livrés

```text
31cbae7a7d0a2c82d6229357f595a62dc269670a20f31e8716e473e47e1d6533  toulouse.png
2350089eb09ae7cb629646756a2563b8ac8bc12b6ca1cecab47bb1395aa63ad4  larochelle.png
5126bf0f7e0abe4576f5b38298cb9bc3f3bb564c4989e3b603bc496be4267d0d  leinster.png
da66e5f8a274e5be39b086182ce238cae8b9bc99833c806c3d2a1eab7cd58289  racing92.png
d10d8d43b40673d564b21d9959af2b8b0aa41ccb3cd34a339e0ba5157667eab2  toulon.png
137c20f947146513d09e63371e8692178e5fcc15033e1e35b6ebefa82f292768  clermont.png
5063a9f4d26b5bf90866a2027ee579f3309832e066a90497b7f52d810cb58ef6  munster.png
fc4c5c349ea5ae474a139958eb9aa91b9a07b30cffbb007ee8ada5709c37ccdb  crusaders.png
```
