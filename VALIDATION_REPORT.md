# Rapport de validation — AlloDocteur V6.1

- Version : 6.1.1
- Architecture : un appel LLM compact, garde-fous P1 déterministes
- Limite de sortie OpenAI : 800 tokens
- Hypothèses cliniques : 0 à 3, uniquement P2/P3/P4
- P1 : aucune hypothèse affichée
- Affichage patient : vérifié
- JSON API compact CLI : vérifié
- Compilation Python : réussie
- Tests automatisés : 27 réussis
- Simulation CLI sans LLM : réussie

## Limite

L'appel OpenAI réel dépend de la clé et du réseau de l'environnement de déploiement.
Le script `scripts/diagnose_openai.py` permet de vérifier l'accès au modèle.
