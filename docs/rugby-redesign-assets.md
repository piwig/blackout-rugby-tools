# Visuels de la direction rugby V2

Créés et inspectés le 30 octobre 2026 pour Blackout Rugby Tools. Génération avec **image_gen intégré** exclusivement ; aucune API ou CLI alternative. Les deux JPEG finaux sont livrés dans le projet. Ce lot ne modifie ni React, ni CSS, ni les crédits existants.

| Fichier public | Dimensions | Taille exacte | Taille indicative | Usage |
| --- | --- | --- | --- | --- |
| `/images/rugby-matchday-v2.jpg` | 1672 × 941 | 274 334 octets | 268 Kio | Grand hero éditorial ; joueurs à droite, ciel libre à gauche |
| `/images/rugby-locker-v2.jpg` | 1672 × 941 | 241 659 octets | 236 Kio | Connexion / tutoriel ; ballon et équipements à droite |

## Direction et contrôles

- Stade : ciel bleu nuit et orange du crépuscule, tribunes chaleureuses, tenues bleu marine et ivoire. Gazon naturellement vert, sans filtre global vert. Poteaux de rugby en H visibles, joueurs génériques vus de dos et foule lointaine anonyme.
- Vestiaire : bois patiné, lumière chaude, maillots rouge brique et marine, ballon ovale sans lacets de football américain, chaussures simples à crampons.
- Les sorties PNG et les JPEG finaux ont été inspectés visuellement. Les JPEG se décodent et conservent leurs dimensions. L'encodage a utilisé le codec JPEG System.Drawing de Windows, qualité 87, sans redimensionnement ni modification artistique.
- La première sortie du stade comportait de minuscules pseudo-inscriptions sur les panneaux et des bandes sur une chaussure. Une retouche ciblée avec image_gen les a remplacées par des surfaces unies ; aucun texte ou logo lisible n'est visible sur le résultat final.
- Les compositions sont générées à partir des prompts ci-dessous, sans photographie de référence externe. Elles représentent des scènes fictives et ne doivent pas être légendées comme un événement réel. Aucun portrait de célébrité n'a été demandé.
- Les photos existantes d'Antoine Dupont, Siya Kolisi et Dan Carter restent distinctes et inchangées.

## Conseils d'intégration

Garder le sujet à droite et utiliser la moitié gauche pour le texte. En grand format, la vue complète conserve les poteaux et les joueurs. Points focaux proposés : `75% 52%` pour le stade, `75% 55%` pour le vestiaire. En recadrage étroit, vérifier la présence du ballon ou des joueurs ; un recadrage trop vertical peut supprimer les poteaux. Un dégradé charbon ou bleu nuit local à gauche peut renforcer la lisibilité sans altérer toute la palette. Vérifier le contraste du texte et le cadrage à la taille réelle dans l'interface : ces contrôles relèvent de l'intégration, pas de la seule validation des fichiers.

## Prompts exacts

### Stade — génération initiale

```text
Use case: photorealistic-natural. Asset type: wide editorial website hero photograph for a premium rugby management application. Primary request: an original rugby union stadium at dusk just before kick-off, realistic full-size white H-shaped rugby goal posts clearly visible against the sky, warm packed stands, dramatic deep midnight-blue evening sky, lit floodlights, crowd rendered as anonymous distant texture. Two generic adult rugby players in deep navy and off-white jerseys seen from behind only, standing on the right side near the sideline and looking toward the field. No identifiable celebrity or actual team. Composition/framing: expansive landscape photograph, 16:9 framing, pitch-level camera, players occupy the right third, left half quieter and darker with open air and pitch for website copy, stadium has believable architecture and pitch lines. Lighting/mood: authentic golden stadium light beneath blue hour, anticipation and understated sports editorial drama, natural photographic color, no artificial green tint. Color palette: midnight blue, charcoal shadows, warm ivory floodlight, natural muted grass, subtle warm brick tones in the stands. Materials/textures: damp short grass, worn jersey fabric, realistic light haze and fine photographic grain. Constraints: original composition, no visible faces, no text, no lettering, no numbers, no logo, no badge, no watermark, no advertising text. Rugby goal must have two vertical uprights joined by one horizontal crossbar with open air above it, never a soccer goal. No American football equipment.
```

### Stade — retouche ciblée

Image de référence : sortie initiale générée, utilisée comme cible d'édition.

```text
Use case: precise-object-edit. Edit target: the supplied rugby stadium dusk photograph. Change only the branding-like details: replace ALL tiny advertising-board lettering along the distant touchline with entirely blank dark charcoal and navy boards; remove the three light stripes on the nearer player's left boot and make all boots completely plain dark leather. Keep everything else unchanged: same two generic players from behind, anatomy, clothing colors, positions, rugby goal posts, sunset, midnight-blue sky, warm stands and floodlights, crop, camera perspective and photographic quality. No text, no lettering, no logos, no brand marks, no watermark anywhere.
```

### Vestiaire — génération

```text
Use case: photorealistic-natural. Asset type: wide editorial website photograph for login and tutorial views of a premium rugby management application. Primary request: original atmospheric rugby changing-room still life with one unbranded oval rugby union ball, a pair of well-worn plain leather studded rugby boots, a solid brick-red jersey loosely draped across a dark navy jersey, all arranged on the right half of an old oak bench. Scene/backdrop: quiet authentic club locker room, warm ivory plaster wall, charcoal wood shadows, subtle pegs, late-afternoon amber light entering through a window outside the frame. Composition/framing: cinematic landscape photograph, 16:9 framing, bench runs from left to right, rugby equipment occupies right two-fifths, generous uncluttered darker wall and bench on the left for website copy; ball is clearly visible in the foreground. Lighting/mood: natural directional warm window light, tactile, quietly proud and inviting, gentle shadow falloff, photographic realism, no green tint. Materials/textures: pebbled off-white rubber ball with simple navy panels and realistic seams, rich worn wood grain, scuffed muddy leather boots with physically plausible metal studs, heavy cotton jersey fabric in brick-red and navy. Constraints: original composition, no people, no faces, no text, no lettering, no numbers, no logo, no badge, no trademarked patterns, no watermark. Ball recognizably rugby-shaped and oval, no American football laces. Boots are completely plain with no stripes or brand symbols.
```

## Traçabilité locale

Masters conservés par l'outil dans son emplacement par défaut ; aucun master existant du projet n'a été écrasé :

- Stade initial : `C:\Users\pieri\.codex\generated_images\01a18e78-9951-7c90-ac45-d0a743adba75\exec-75a3f1f4-ff15-4ecb-ac90-b6430a62996d.png`
- Stade retenu après retouche : `C:\Users\pieri\.codex\generated_images\01a18e78-9951-7c90-ac45-d0a743adba75\exec-8f635505-384d-47be-bfb7-c7e05814f803.png`
- Vestiaire retenu : `C:\Users\pieri\.codex\generated_images\01a18e78-9951-7c90-ac45-d0a743adba75\exec-e92d6d8d-3c4b-4ecf-9a09-d1d0136d9b7a.png`

## Entrées de crédits proposées

À intégrer par le coordinateur dans le catalogue et l'affichage utilisateur des crédits. Aucune licence Creative Commons tierce n'est attribuée à ces générations.

```json
[
  {
    "src": "/images/rugby-matchday-v2.jpg",
    "name": "Avant le match — stade de rugby au crépuscule",
    "author": "Visuel généré avec OpenAI Image Generation pour Blackout Rugby Tools",
    "license": "Visuel original généré par IA — aucune licence de banque d’images tierce",
    "sourceUrl": null,
    "licenseUrl": null,
    "changes": "Génération originale puis retouche des panneaux et chaussures pour retirer les détails évoquant des marques ; encodage JPEG qualité 87. Illustration photoréaliste, pas photographie documentaire.",
    "width": 1672,
    "height": 941,
    "focalPoint": "75% 52%",
    "verifiedOn": "2026-10-30"
  },
  {
    "src": "/images/rugby-locker-v2.jpg",
    "name": "Au vestiaire — ballon, crampons et maillots",
    "author": "Visuel généré avec OpenAI Image Generation pour Blackout Rugby Tools",
    "license": "Visuel original généré par IA — aucune licence de banque d’images tierce",
    "sourceUrl": null,
    "licenseUrl": null,
    "changes": "Génération originale puis encodage JPEG qualité 87. Illustration photoréaliste, pas photographie documentaire.",
    "width": 1672,
    "height": 941,
    "focalPoint": "75% 55%",
    "verifiedOn": "2026-10-30"
  }
]
```

