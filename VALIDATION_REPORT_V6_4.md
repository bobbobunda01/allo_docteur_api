# Rapport de validation logicielle — AlloDocteur V6.4

## Résultat

- Version : 6.4.0
- Questionnaire : inchangé
- API publique : structure principale conservée
- Tests automatisés : 43/43 réussis
- Stress-test : 110 domaines médicaux
- Détection locale des red flags injectés : 110/110
- Détection fallback des red flags injectés : 110/110

## Corrections majeures depuis V6.3

- extension de la détection locale aux 17 familles P1 dans le texte libre ;
- gestion de négations fréquentes ;
- garde-fou pédiatrique et obstétrical ;
- plancher de priorité épidémiologique basé uniquement sur des alertes explicitement fournies et datées ;
- refus d'utiliser une alerte obsolète pour relever la priorité ;
- fallback conservateur indépendant du LLM ;
- LLM V6.4 capable d'exprimer `uncertainty`, `requires_human_review`, `epidemiology_risk_notes` et `infection_control_precautions` ;
- contradictions LLM entraînant une revue humaine.

## Limites

Ce rapport est une validation logicielle interne. Les tests sont synthétiques et ne remplacent pas :

- une revue du corpus et des seuils par des médecins ;
- une validation clinique indépendante ;
- des tests multilingues et dialectaux ;
- une étude de sensibilité/spécificité sur cas réels annotés ;
- des procédures réglementaires, de cybersécurité, de protection des données et de gouvernance clinique.
