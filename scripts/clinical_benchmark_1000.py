from __future__ import annotations

import csv
import json
import time
from pathlib import Path

from clinical.epidemiology_safety_gate import evaluate_epidemiology_safety
from clinical.population_safety_gate import evaluate_population_safety
from clinical.text_safety_gate import evaluate_text_safety
from domain.models import IntakeAnswers
from services.triage_service import TriageService

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / 'benchmark' / 'allodocteur_cvb_1000.jsonl'
OUT_DIR = ROOT / 'benchmark_results_v641'


def run(dataset: Path = DEFAULT_DATASET) -> dict:
    OUT_DIR.mkdir(exist_ok=True)
    service = TriageService()
    rows = []
    with dataset.open(encoding='utf-8') as f:
        for line in f:
            case = json.loads(line)
            intake = IntakeAnswers.model_validate(case['input'])
            t0 = time.perf_counter()
            text_gate = evaluate_text_safety(intake.complaint_text, intake.associated_signs)
            pop_gate = evaluate_population_safety(intake)
            epi_gate = evaluate_epidemiology_safety(intake)
            decision = service.triage(intake)
            elapsed = (time.perf_counter() - t0) * 1000
            actual_p1 = decision.priority.value == 'P1'
            rows.append({
                'case_id': case['case_id'], 'domain': case['domain'], 'kind': case['kind'],
                'expected_priority': case['expected_priority'], 'expected_p1': case['expected_p1'],
                'expected_red_flag': case.get('expected_red_flag') or '', 'alert': case.get('alert') or '',
                'complaint_text': intake.complaint_text,
                'text_gate_p1': text_gate.emergency, 'population_p1': pop_gate.emergency,
                'epi_floor': epi_gate.priority_floor or '', 'actual_priority': decision.priority.value,
                'actual_p1': actual_p1, 'llm_used': decision.llm_used, 'mode': decision.extraction_mode,
                'severity_codes': '|'.join(decision.severity_signs_triggered),
                'correct_p1_binary': actual_p1 == bool(case['expected_p1']),
                'correct_exact_priority': decision.priority.value == case['expected_priority'],
                'elapsed_ms': round(elapsed, 3),
            })

    def save(name, subset):
        path = OUT_DIR / name
        with path.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader(); w.writerows(subset)
        return path

    save('allodocteur_cvb_1000_results.csv', rows)
    p1 = [r for r in rows if r['expected_p1']]
    non = [r for r in rows if not r['expected_p1']]
    fn = [r for r in p1 if not r['actual_p1']]
    fp = [r for r in non if r['actual_p1']]
    save('false_negatives.csv', fn); save('false_positives.csv', fp)
    metrics = {
        'n': len(rows), 'p1_expected': len(p1), 'non_p1_expected': len(non),
        'p1_true_positive': len(p1)-len(fn), 'p1_false_negative': len(fn),
        'p1_false_positive': len(fp), 'p1_true_negative': len(non)-len(fp),
        'sensitivity_p1': (len(p1)-len(fn))/len(p1),
        'specificity_p1': (len(non)-len(fp))/len(non),
        'undertriage_p1': len(fn)/len(p1), 'overtriage_p1': len(fp)/len(non),
        'exact_priority_accuracy': sum(r['correct_exact_priority'] for r in rows)/len(rows),
        'llm_used_cases': sum(bool(r['llm_used']) for r in rows),
    }
    by_flag = {}
    for flag in sorted({r['expected_red_flag'] for r in p1 if r['expected_red_flag']}):
        grp = [r for r in p1 if r['expected_red_flag'] == flag]
        by_flag[flag] = {'n': len(grp), 'detected': sum(r['actual_p1'] for r in grp),
                         'sensitivity': sum(r['actual_p1'] for r in grp)/len(grp)}
    metrics['by_red_flag'] = by_flag
    (OUT_DIR/'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return metrics

if __name__ == '__main__':
    import sys
    run(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATASET)
