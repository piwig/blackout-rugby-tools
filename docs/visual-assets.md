# Visuels rugby

Visuels préparés le 30 octobre 2026, puis complétés pour le lot parcours, profil et progression. Les sections ci-dessous distinguent les photographies documentaires, les créations synthétiques BRT et les marques réelles des clubs.

| Fichier public | Dimensions | Poids | Usage recommandé |
| --- | --- | --- | --- |
| `/images/antoine-dupont-2023.jpg` | 1280 × 878 | 310 Ko | Bannière éditoriale du tableau de bord ; point focal `38% 42%` |
| `/images/siya-kolisi-2022.jpg` | 960 × 1208 | 320 Ko | Carte portrait / leadership ; point focal `50% 28%` |
| `/images/dan-carter-2015.jpg` | 1280 × 853 | 235 Ko | Carte tactique / précision ; point focal `56% 48%` |
| `/images/rugby-ball-hero.jpg` | 1536 × 1024 | 262 Ko | Hero de connexion ; texte sur la moitié gauche, ballon à droite |
| `/images/rugby-ball-hero.png` | 1536 × 1024 | 2,25 Mo | Master du visuel généré ; préférer le JPEG pour servir la page |

## Provenance et affichage des crédits

Les métadonnées prêtes pour l'interface figurent dans `web/public/image-credits.json`. Afficher dans une zone « Crédits photos » accessible le titre/nom, l'auteur, un lien vers la fiche source, le nom et le lien de la licence ainsi que la mention des modifications. Un JSON seul ne remplace pas cet affichage utilisateur.

- [Antoine Dupont](https://commons.wikimedia.org/wiki/File:AntoineDupont2023kick(cropped).jpg) : **Stefano Delfrate (stede64), CC BY-SA 2.0**. Recadrage Commons par AideDésintéressée. La miniature officielle est téléchargée telle quelle.
- [Siya Kolisi](https://commons.wikimedia.org/wiki/File:Siya_Kolisi_2022.jpg) : **Stefano Delfrate, CC BY-SA 2.0**. Recadrage Commons par Stemoc. La miniature officielle est téléchargée telle quelle.
- [Dan Carter](https://commons.wikimedia.org/wiki/File:Dan_Carter_2015_RWC.jpg) : **quintinsmith_ip, CC BY 2.0**. La miniature officielle est téléchargée telle quelle.

Les fiches Commons affichent explicitement ces licences et les auteurs. Pour les deux photos CC BY-SA, conserver cette licence pour les versions adaptées des images et indiquer tout nouveau recadrage ou traitement. Les photos montrent naturellement des écussons et publicités présents pendant les matchs ; aucun filigrane photographique n'a été détecté à l'inspection. Présenter les joueurs dans un contexte rugby éditorial, sans suggérer qu'ils soutiennent l'application. Le ballon généré ne comporte ni personne réelle, ni marque, ni texte.

## Génération du ballon

Outil utilisé : **image_gen intégré** (pas de CLI/API externe). Une génération unique, inspectée visuellement. Le PNG a été copié dans le dossier public, puis une version JPEG de même taille a été encodée à qualité 88 pour limiter le poids. Aucun compositing ou faux portrait.

Prompt exact :

> Use case: photorealistic-natural. Asset type: wide website hero photograph for a premium rugby club management app. Primary request: an original atmospheric close-up of a single unbranded rugby union ball resting on damp short grass beside a white painted touchline, empty rugby pitch and distant goal posts softly out of focus. Landscape 3:2 framing. Ball near the right third of the image, left half darker and uncluttered for website copy. Oval white textured rugby ball with simple deep forest green panels, realistic seams and tiny dew droplets. Early evening natural light, subdued warm highlights, rich forest green #183c30 grass shadows and cream highlights. Editorial sports photography, understated, tactile, confident, sophisticated. No people, no brand logo, no lettering, no numerals, no watermark. The rugby ball must be recognizably oval, no soccer ball, no American football laces. Original composition, not a recognizable existing photograph.

## Contrôles

Les quatre visuels ont été ouverts et inspectés. Dimensions lues dans les fichiers décodés ; fichiers non vides ; JPEG Wikimedia conservés sans retouche. Le visuel généré et sa version JPEG ont été inspectés. Les titres, auteurs et licences ont été comparés aux fiches Commons. Les URLs de téléchargement ont été observées en suivant les liens de résolutions proposés par Commons, sans reconstruire de chemin de miniature.

À l'intégration, conserver le ballon visible dans les recadrages mobile et prévoir un voile vert sombre pour la lisibilité du texte du hero. Les photos sportives sont volontairement secondaires ; les données de gestion restent le contenu principal du tableau de bord.

## Direction photographique renforcée — 30 octobre 2026

La demande utilisateur de dépasser le vert uniforme remplace la recommandation initiale de photographies secondaires sous voile vert. Le stade original et le vestiaire sont désormais les scènes principales ; les photos de joueurs gardent leurs couleurs naturelles. Navigation charbon, papier ivoire, accents brique/ocre/bleu. Les dégradés derrière le texte sont neutres ; les tableaux restent sur des surfaces unies.

Fichiers de cette première refonte et prompts exacts : [visuels de la refonte rugby](rugby-redesign-assets.md). Crédits IA et recadrages CSS ajoutés au catalogue visible. Les JPEG historiques ne sont pas modifiés.

## Identité BRT et bannières du lot parcours

Trois créations originales supplémentaires ont été réalisées avec **ImageGen intégré**, sans recours à une banque d’images ni à des photos d’un lieu identifié. Le logo est un dessin de blason de rugby sans lettres ; les deux scènes sont des illustrations photoréalistes synthétiques, sans marque de club. Elles ne documentent pas un stade ou un vestiaire réel.

| Fichier livré | Dimensions | Octets | Usage |
| --- | --- | ---: | --- |
| [brt-logo-48.png](../web/public/images/brt-logo-48.png) | 48 × 48, PNG avec alpha | 4 701 | Favicon PNG |
| [brt-logo-180.png](../web/public/images/brt-logo-180.png) | 180 × 180, PNG avec alpha | 37 350 | Icône Apple |
| [brt-logo-192.png](../web/public/images/brt-logo-192.png) | 192 × 192, PNG avec alpha | 41 452 | Marque dans l’interface, avatar Rugby BRT et manifeste |
| [brt-logo-512.png](../web/public/images/brt-logo-512.png) | 512 × 512, PNG avec alpha | 199 377 | Icône de grande taille et manifeste |
| [brt-favicon.ico](../web/public/images/brt-favicon.ico) | Conteneur ICO | 15 480 | Favicon alternatif |
| [brt-banner-matchday.jpg](../web/public/images/brt-banner-matchday.jpg) | 1920 × 800, JPEG RGB | 217 998 | Bannière « Jour de match » |
| [brt-banner-clubhouse.jpg](../web/public/images/brt-banner-clubhouse.jpg) | 1920 × 800, JPEG RGB | 221 692 | Bannière « Vie du club » |

Les dimensions et formats PNG/JPEG ont été relus dans les fichiers ; le poids de chaque fichier a été relevé sur disque. Les dérivés sont des conversions et redimensionnements des générations initiales. Les PNG conservent un canal alpha. L’interface utilise le logo de 192 px ; les icônes et couleurs sont référencées par [index.html](../web/index.html) et le [manifeste](../web/public/manifest.webmanifest). Les crédits des trois créations sont présents dans [image-credits.json](../web/public/image-credits.json).

### Provenance des générations

Les maîtres restent hors dépôt dans la session locale `C:\Users\pieri\.codex\generated_images\01a18de5-548e-77a3-a09e-6d0c2573d70f`. Les descriptions suivantes résument les demandes de génération ; elles ne sont pas des transcriptions exactes des prompts.

| Création | Fichier maître dans la session | Résumé de la demande |
| --- | --- | --- |
| Emblème BRT | `exec-0915e144-2ed2-47d1-975f-7792843d0903.png` | Blason à dessin plat, ballon ovale de rugby et poteaux ; or `#DAB66E`, ivoire `#F7F2E7`, bleu nuit `#17212B` ; fond transparent, sans lettres. |
| Jour de match | `exec-9dd9c49c-f215-4ad6-98fc-8c8e3520539b.png` | Scène photoréaliste originale à l’entrée d’un terrain depuis un tunnel de stade ; partie gauche sombre et dégagée pour le texte ; sans marque de club. |
| Vie du club | `exec-5c9da56c-2a9b-4cd1-888f-37c35fbc7b5b.png` | Vestiaire en bois photoréaliste original ; ambiance rugby, partie gauche sombre et dégagée pour le texte ; sans marque de club. |

### Avatars et club de cœur

Les quatre propositions d’avatar utilisent les icônes Lucide `Shirt`, `Shield`, `Trophy` et le logo BRT local. Aucun SVG, URL ou fichier fourni par un manager n’est accepté comme avatar. Le numéro, les initiales et le club de cœur se règlent séparément dans le profil.

Les huit marques de Toulouse, La Rochelle, Leinster, Racing 92, Toulon, Clermont, Munster et Crusaders proviennent de sources officielles ; elles n’ont pas été générées. Le [catalogue et ses preuves de provenance](rugby-club-assets.md) précise les traitements, dimensions et conditions de présentation. Leur présence indique une préférence personnelle, sans affiliation de BRT aux clubs. Les variantes comportant du blanc sont posées sur une surface sombre, et les proportions sont conservées.

Les [captures locales du lot parcours](experience-2026-10-30.md#captures-du-parcours) documentent l’intégration. Les contrôles sur la version publique restent à consigner dans le [suivi du déploiement](deployment.md).
