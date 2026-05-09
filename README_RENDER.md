# AlloDocteur API — Projet prêt pour Render

## Structure

```text
allodocteur_render_ready/
├── app/
│   ├── main.py                    # Entrée FastAPI : app.main:app
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   └── engine/                # Tous les moteurs AlloDocteur historiques
│   ├── models/
│   │   └── schemas.py
│   ├── routes/
│   │   └── triage.py
│   ├── services/
│   │   └── triage_service.py
│   └── utils/
│       └── logging_utils.py
├── data/
│   └── kb_allodocteur_v3_complete.json   # À ajouter
├── Dockerfile
├── render.yaml
├── requirements.txt
└── .env.example
```

## Étape obligatoire

Copie ta base de connaissances dans :

```text
data/kb_allodocteur_v3_complete.json
```

Sans ce fichier, `/health` renverra `degraded` et `/triage` refusera de traiter.

## Exécution locale

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Test :

```bash
curl http://localhost:8000/health
```

## Test triage

```bash
curl -X POST http://localhost:8000/triage \
-H "Content-Type: application/json" \
-H "X-API-Key: test_key" \
-d '{
  "complaint_text": "j ai mal au ventre et un peu de fievre",
  "duration_choice": "1_3_days",
  "associated_signs": ["Fièvre"],
  "medical_history": [],
  "date_of_birth": "22/08/2000",
  "sex": "Homme",
  "province": "Kinshasa",
  "immediate_red_flags": {}
}'
```

## Déploiement Render

### Option recommandée : Docker

1. Crée un repository GitHub avec ce dossier.
2. Ajoute `data/kb_allodocteur_v3_complete.json`.
3. Sur Render : New + Web Service.
4. Sélectionne le repo.
5. Render détectera `render.yaml`.
6. Dans Environment Variables, ajoute :

```text
API_KEY=ta_cle_secrete
ALLODOCTEUR_KB_PATH=data/kb_allodocteur_v3_complete.json
```

Render utilisera :

```bash
uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
```

## Pourquoi cette structure corrige ton problème

Les fichiers moteur ne sont plus à plat sans logique. Ils sont regroupés dans :

```text
app/core/engine/
```

Le service `app/services/triage_service.py` ajoute ce dossier au `sys.path` pour garder les imports historiques compatibles sans réécrire toute la pile V3.3 → V3.9.
