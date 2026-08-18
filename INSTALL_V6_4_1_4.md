# Installation V6.4.1.4

## Recommandé
Utiliser le dossier complet V6.4.1.4.

```bash
unzip AlloDocteur_V6_4_1_4_Composite_Safety_Patterns.zip
cd AlloDocteur_V6_4_1_4_Composite_Safety_Patterns
```

Reprendre votre `.env` local (ne jamais mettre la clé API dans le code), puis :

```bash
python -m pytest -q
python -m cli.interactive
```

## Régression Lot 4A
Copier `test_batch_04a.py` et `batch_04a_cases.json` dans la racine puis :

```bash
python test_batch_04a.py
```

Comparer en priorité : sensibilité P1, spécificité P1, P1->P2, P2->P1 et les cas B04A-012, 017, 018, 040, 064 et 066.
Le cas B04A-056 doit être revu séparément car son Gold Standard P2 est cliniquement discutable.
