# Checklist de déploiement — AlloDocteur V6

- [ ] Exécuter `python scripts/diagnose_openai.py` et obtenir `Responses API : OK`.
- [ ] Utiliser une clé OpenAI de projet stockée dans un gestionnaire de secrets.
- [ ] Conserver `OPENAI_MAX_RETRIES=0` et un timeout borné.
- [ ] Configurer `ENVIRONMENT=production`, les hôtes et CORS.
- [ ] Protéger la route technique avec `ADMIN_API_TOKEN`.
- [ ] Centraliser et superviser `runtime/logs/allodocteur.log`.
- [ ] Définir une politique de conservation des audits et données médicales.
- [ ] Tester les 17 signes de sévérité et le filet textuel P1.
- [ ] Valider cliniquement P1/P2/P3/P4 et l'orientation des spécialités.
- [ ] Réaliser des tests de charge, réseau lent, quota et indisponibilité OpenAI.
- [ ] Prévoir un protocole de revue humaine et de gestion des incidents.

Cette checklist est technique. Elle ne remplace pas la validation médicale, juridique et réglementaire.
