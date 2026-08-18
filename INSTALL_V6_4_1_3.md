# Installation V6.4.1.3

La méthode recommandée est d'utiliser le dossier V6.4.1.3 complet plutôt que de
remplacer manuellement des fichiers dans V6.4.1.2.

## 1. Décompresser

```bash
unzip AlloDocteur_V6_4_1_3_P1_Capable_Safety_Fusion.zip
cd AlloDocteur_V6_4_1_3_P1_Capable_Safety_Fusion
```

## 2. Reprendre uniquement votre configuration secrète

Ne copiez pas une clé API dans le code. Reprenez votre `.env` local ou exportez :

```bash
export OPENAI_API_KEY="..."
export OPENAI_MODEL="gpt-5-mini"
```

## 3. Vérifier les tests

```bash
python -m pytest -q
```

## 4. Test interactif

```bash
python -m cli.interactive
```

## 5. Rejouer Lot 4A

Copiez dans la racine :
- `test_batch_04a.py`
- `batch_04a_cases.json`

Puis :

```bash
python test_batch_04a.py
```

Comparez notamment :
- sensibilité P1 ;
- spécificité P1 ;
- P1 -> P2 ;
- P2 -> P1 ;
- spécialité acceptable ;
- `severity_override` ;
- `llm_direct_p1`.

Ne modifiez pas les cas du Lot 4A avant ce test de régression.
