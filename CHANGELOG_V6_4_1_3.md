# AlloDocteur V6.4.1.3 — P1-Capable Safety Fusion

## Cause racine corrigée

Dans V6.4.1.2, le schéma JSON strict du LLM limitait `priority` à `P2`, `P3`, `P4`.
Le LLM pouvait reconnaître une situation grave, mais ne pouvait pas produire `P1`
comme priorité structurée. Le backend ne produisait alors P1 que si un garde-fou
déterministe ou `detected_severity_signs` s'activait.

Le Lot 4A a montré 10 P1 classés P2, tous avec :
`Safety local non déclenchée + LLM final non-P1`.

## Corrections

1. `llm/schemas.py`
   - `priority` accepte maintenant `P1`, `P2`, `P3`, `P4`.

2. `llm/prompts.py`
   - le LLM reçoit explicitement la responsabilité de reconnaître P1 dans le texte libre ;
   - distinction P1/P2 clarifiée ;
   - obligation de documenter les codes de gravité lorsqu'ils sont identifiables.

3. `services/triage_service.py`
   - fusion protectrice conservée ;
   - une décision LLM explicite P1 impose désormais P1 même si l'extraction d'un code
     de sévérité est vide ;
   - `llm_direct_p1` est enregistré dans les métadonnées ;
   - aucun P1 local ne peut être abaissé.

4. Le routage de spécialité par le LLM est conservé.

## Important

Cette version est une version d'évaluation. Elle n'est pas validée pour une utilisation
clinique autonome. Après installation :
- rejouer Lot 4A comme test de régression ;
- ne pas modifier le Gold Standard ;
- lancer ensuite un Lot 4B entièrement nouveau pour mesurer la généralisation.
