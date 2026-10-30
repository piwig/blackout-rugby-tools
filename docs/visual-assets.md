# Visuels rugby

Préparés et inspectés le 30 octobre 2026. Le code de l'application n'a pas été modifié par ce lot.

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

Nouveaux fichiers et prompts exacts : docs/rugby-redesign-assets.md. Crédits IA et recadrages CSS ajoutés au catalogue visible. Les JPEG historiques ne sont pas modifiés.
