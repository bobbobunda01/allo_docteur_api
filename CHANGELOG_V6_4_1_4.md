# AlloDocteur V6.4.1.4 — Composite Safety Patterns

Cette version conserve V6.4.1.3 (LLM capable de produire P1) et ajoute une correction ciblée de la Safety locale.

## Nouveaux patterns composites P1

1. **Menace des voies aériennes supérieures** : stridor/bruit inspiratoire + bave ou incapacité/refus d'avaler.
2. **Détresse respiratoire** : dyspnée au repos + limitation de la parole.
3. **Asthme sévère** : asthme connu + échec du traitement de secours + lutte respiratoire.
4. **Syndrome cholinergique sur pesticide** : exposition + au moins deux familles de signes cholinergiques + atteinte respiratoire/neurologique.

Ces règles réutilisent uniquement les codes existants `severe_breathing` et `poisoning`.

## Anti-surtriage

- `voix étouffée` n'est plus confondue avec `étouffement`.
- une respiration explicitement normale bloque les nouveaux patterns respiratoires composites.
- une articulation rouge/chaude/gonflée avec fièvre reste P2 par défaut en l'absence de signe systémique sévère.
- aucun mot isolé ne suffit à déclencher les quatre nouveaux patterns composites.

## Inchangé

- questionnaire ;
- contrat des 17 codes de gravité ;
- capacité LLM P1/P2/P3/P4 ;
- routage de spécialité par le LLM ;
- population safety et epidemiology safety ;
- fusion protectrice : aucune source P1 ne peut être abaissée.

Cette version reste une version d'évaluation et ne remplace pas une validation clinique indépendante.
