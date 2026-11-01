# Vérification de la version 2.9.1

Version publiée le 1 novembre 2026, code `ed788f4`.

- Suite Python complète : 980 tests réussis.
- Suite Node complète : 120 tests réussis.
- Compilation TypeScript et build Vite réussis.
- Catalogues FR/EN/ES/IT : 3019 clés, aucune entrée manquante, supplémentaire ou invalide.
- Revue indépendante : trois anomalies de provenance temporelle détectées puis corrigées et revérifiées par les endpoints publics sur données synthétiques.
- Vérification navigateur : groupes d’équipes, sélection active/suspendue, progression U20 sans académie de club, retour vers un affilié, création d’un événement U20 et persistance après rechargement.
- Publication : sauvegardes avant/après, contrôle d’intégrité SQLite et migration additive, version santé 2.9.1, trente fichiers statiques conformes au build, HTTPS et en-têtes de sécurité, refus des API privées sans connexion, CAPTCHA toujours actif.

Les avertissements déjà présents de dépréciation Starlette/httpx et de taille de bundle Vite restent à traiter séparément. Le format réel d’une réponse NT propriétaire n’a pas été validé dans ce lot ; les tests U20/NT et multi-clubs utilisent des données synthétiques. Les détails des comptes, captures et journaux de publication restent privés.
