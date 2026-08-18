# Déploiement Render — AlloDocteur

Ce dossier est prêt pour un **Render Web Service** via Docker.

## Méthode recommandée
1. Pousser ce dossier dans un dépôt Git privé (GitHub/GitLab).
2. Dans Render, créer un **Blueprint** à partir du dépôt : `render.yaml` sera détecté.
3. Dans les variables d'environnement Render, renseigner `OPENAI_API_KEY` comme secret.
4. Déployer.
5. Vérifier `GET /v1/health`.
6. L'API publique de triage reste `POST /v1/triage`.

## Sécurité
- Le fichier `.env` local n'est pas nécessaire sur Render et n'est pas inclus dans le paquet de déploiement fourni.
- Ne jamais committer une vraie clé `OPENAI_API_KEY` dans Git.
- `ENVIRONMENT=production` désactive `/docs` et `/redoc` selon la configuration actuelle.
- `ALLOWED_HOSTS=["*"]` est utilisé pour accepter le hostname dynamique de Render. Restreindre cette valeur plus tard si un domaine fixe est utilisé.

## Stockage runtime
Les journaux/audits sous `runtime/` sont éphémères sur un service Render standard. Utiliser un disque persistant ou un stockage externe si leur conservation est obligatoire.
