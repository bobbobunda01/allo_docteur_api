# Changelog

## 6.4.1 — Safety Hardening

- Correction des 265 faux négatifs et 61 faux positifs analysés dans le CVB-1000 V6.4.
- Extension du NLP déterministe P1 aux paraphrases et fautes fréquentes.
- Détection composite fièvre/nuque raide et fièvre/éruption afin de réduire le sur-triage.
- Renforcement des négations dans le Text Safety Gate et Population Safety Gate.
- Ajout du runner CVB-1000 et d'un corpus clean sans fuite d'étiquette de domaine.
- Résultat de régression CVB-1000 clean : 500/500 P1 et 500/500 non-P1 correctement séparés en mode local/fallback.
- 51 tests pytest réussis.


## 6.1.1

- Passage de `OPENAI_MAX_OUTPUT_TOKENS` à 800.
- Ajout de `possible_conditions` (maximum 3).
- Ajout de `diagnostic_disclaimer`.
- Hypothèses masquées automatiquement pour P1.
- Ajout des hypothèses au bloc patient.
- Ajout de `specialty`, `possible_conditions` et `diagnostic_disclaimer` au JSON CLI.
- Prompt raccourci et encadré pour éviter les diagnostics affirmatifs.

## 6.4.0 — Clinical & Epidemiological Safety
- Questionnaire utilisateur conservé.
- Clinical Text Safety V2 avec couverture des 17 red flags et négations fréquentes.
- Population Safety : pédiatrie, grossesse, prudence gériatrique.
- Epidemiology Safety : alertes explicites datées, plancher P2, infection-control et revue humaine.
- Fallback safety-only conservateur indépendant du LLM.
- Contrat LLM enrichi : incertitude, revue humaine, risque épidémiologique, précautions infection-control.
- Safety Fusion étendue sans suppression de la puissance de raisonnement du LLM.
- 43 tests pytest réussis et stress-test 110 domaines à 110/110 sur red flags synthétiques.
