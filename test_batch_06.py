from __future__ import annotations
import csv, json, os, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT/".env")
    load_dotenv()
except Exception:
    pass

DATASET=ROOT/"batch_06_cases.json"
OUT_JSON=ROOT/"batch_06_gpt5mini_results.json"
OUT_CSV=ROOT/"batch_06_gpt5mini_results.csv"
SUMMARY_JSON=ROOT/"batch_06_gpt5mini_summary.json"
P1_FN_JSON=ROOT/"batch_06_p1_false_negatives.json"
DANGEROUS_JSON=ROOT/"batch_06_dangerous_errors.json"
ALL_ERRORS_JSON=ROOT/"batch_06_priority_errors.json"

if not DATASET.exists():
    raise SystemExit(f"Fichier introuvable: {DATASET}")
if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("OPENAI_API_KEY absente.")

from domain.models import IntakeAnswers
from services.triage_service import TriageService
from app.settings import settings

cases=json.loads(DATASET.read_text(encoding="utf-8"))
service=TriageService()
rows=[]

RANK={"P4":0,"P3":1,"P2":2,"P1":3}

def norm(s):
    return " ".join(str(s or "").casefold().replace("’","'").split())

def spec_ok(actual, accepted):
    a=norm(actual)
    return any(a==norm(x) for x in accepted)

def orient_ok(expected_priority, orientation):
    o=norm(orientation)
    if expected_priority=="P1":
        return any(k in o for k in ["urgence","immédiat","immediat","hôpital","hopital"])
    if expected_priority=="P2":
        return any(k in o for k in ["prioritaire","rapide","24","48"])
    if expected_priority=="P3":
        return any(k in o for k in ["consult","médecin","medecin","programm"])
    if expected_priority=="P4":
        return any(k in o for k in ["surveillance","conseil","domicile","auto","persistance","aggravation"])
    return False

print(f"AlloDocteur model={settings.openai_model} | Lot 6 | cases={len(cases)}")

for i,case in enumerate(cases,1):
    gold=case["gold"]
    expected=gold["expected_priority"]
    acceptable=gold["acceptable_priorities"]
    intake=IntakeAnswers.model_validate(case["input"])
    t0=time.perf_counter()
    try:
        d=service.triage(intake)
        elapsed=time.perf_counter()-t0
        actual=d.priority.value
        actual_spec=d.specialty_orientation.primary_specialty
        delta=RANK[actual]-RANK[expected]
        dangerous_undertriage = (
            (expected=="P1" and actual!="P1")
            or delta <= -2
        )
        row={
            "case_id":case["case_id"],
            "domain":case["domain"],
            "expected_priority":expected,
            "acceptable_priorities":acceptable,
            "actual_priority":actual,
            "strict_priority_correct":actual==expected,
            "clinically_acceptable_priority":actual in acceptable,
            "priority_delta":delta,
            "dangerous_undertriage":dangerous_undertriage,
            "accepted_specialties":gold["accepted_specialties"],
            "actual_specialty":actual_spec,
            "specialty_acceptable":spec_ok(actual_spec,gold["accepted_specialties"]),
            "expected_orientation":gold["expected_orientation"],
            "actual_orientation":d.orientation,
            "orientation_level_correct":orient_ok(expected,d.orientation),
            "clinical_rationale":gold["clinical_rationale"],
            "llm_used":bool(d.llm_used),
            "mode":d.extraction_mode,
            "severity_override":bool(d.severity_override_applied),
            "human_review":bool(d.requires_human_review),
            "possible_conditions":list(d.possible_conditions),
            "contradictions":list(d.contradictions),
            "elapsed_seconds":round(elapsed,3),
            "error":""
        }
    except Exception as exc:
        elapsed=time.perf_counter()-t0
        row={
            "case_id":case["case_id"],"domain":case["domain"],
            "expected_priority":expected,"acceptable_priorities":acceptable,
            "actual_priority":"ERROR","strict_priority_correct":False,
            "clinically_acceptable_priority":False,"priority_delta":None,
            "dangerous_undertriage":expected=="P1",
            "accepted_specialties":gold["accepted_specialties"],
            "actual_specialty":"ERROR","specialty_acceptable":False,
            "expected_orientation":gold["expected_orientation"],
            "actual_orientation":"ERROR","orientation_level_correct":False,
            "clinical_rationale":gold["clinical_rationale"],
            "llm_used":False,"mode":"error","severity_override":False,
            "human_review":True,"possible_conditions":[],"contradictions":[],
            "elapsed_seconds":round(elapsed,3),
            "error":f"{type(exc).__name__}: {exc}"
        }
    rows.append(row)
    print(
        f"[{i:03d}/{len(cases)}] {row['case_id']} "
        f"exp={expected} got={row['actual_priority']} "
        f"acceptable={row['clinically_acceptable_priority']} "
        f"mode={row['mode']}"
    )

OUT_JSON.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")

fields=[
"case_id","domain","expected_priority","actual_priority","strict_priority_correct",
"clinically_acceptable_priority","priority_delta","dangerous_undertriage",
"actual_specialty","specialty_acceptable","expected_orientation","actual_orientation",
"orientation_level_correct","llm_used","mode","severity_override","human_review",
"elapsed_seconds","error"
]
with OUT_CSV.open("w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
    for r in rows:
        w.writerow({k:r.get(k,"") for k in fields})

valid=[r for r in rows if not r["error"]]

def metrics(sub):
    if not sub:
        return {"n":0}
    p1=[r for r in sub if r["expected_priority"]=="P1"]
    nonp1=[r for r in sub if r["expected_priority"]!="P1"]
    tp=sum(r["actual_priority"]=="P1" for r in p1)
    fn=len(p1)-tp
    fp=sum(r["actual_priority"]=="P1" for r in nonp1)
    tn=len(nonp1)-fp
    return {
        "n":len(sub),
        "strict_priority_accuracy":sum(r["strict_priority_correct"] for r in sub)/len(sub),
        "clinical_priority_acceptability":sum(r["clinically_acceptable_priority"] for r in sub)/len(sub),
        "specialty_acceptability":sum(r["specialty_acceptable"] for r in sub)/len(sub),
        "orientation_accuracy":sum(r["orientation_level_correct"] for r in sub)/len(sub),
        "dangerous_undertriage_rate":sum(r["dangerous_undertriage"] for r in sub)/len(sub),
        "mean_elapsed_seconds":sum(r["elapsed_seconds"] for r in sub)/len(sub),
        "p1_gold_n":len(p1),
        "p1_sensitivity":tp/(tp+fn) if tp+fn else None,
        "p1_specificity":tn/(tn+fp) if tn+fp else None,
        "p1_fn":fn,
        "p1_fp":fp,
    }

summary={
    "model":settings.openai_model,
    "benchmark":"Lot 6 clinical-range benchmark",
    "n_cases":len(rows),
    "completed":len(valid),
    "errors":len(rows)-len(valid),
    "overall":metrics(valid),
    "llm_only":metrics([r for r in valid if r["llm_used"]]),
    "fallback_only":metrics([r for r in valid if not r["llm_used"] and r["mode"]=="fallback"]),
    "mode_counts":{},
    "confusion":{},
    "per_expected_priority":{},
    "clinical_acceptability_by_priority":{},
}

for r in valid:
    summary["mode_counts"][r["mode"]]=summary["mode_counts"].get(r["mode"],0)+1
    key=f"{r['expected_priority']}->{r['actual_priority']}"
    summary["confusion"][key]=summary["confusion"].get(key,0)+1

for p in ["P1","P2","P3","P4"]:
    sub=[r for r in valid if r["expected_priority"]==p]
    summary["per_expected_priority"][p]=metrics(sub)

p1fn=[r for r in valid if r["expected_priority"]=="P1" and r["actual_priority"]!="P1"]
dangerous=[r for r in valid if r["dangerous_undertriage"]]
errors=[r for r in valid if not r["strict_priority_correct"]]

P1_FN_JSON.write_text(json.dumps(p1fn,ensure_ascii=False,indent=2),encoding="utf-8")
DANGEROUS_JSON.write_text(json.dumps(dangerous,ensure_ascii=False,indent=2),encoding="utf-8")
ALL_ERRORS_JSON.write_text(json.dumps(errors,ensure_ascii=False,indent=2),encoding="utf-8")
SUMMARY_JSON.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")

print("\n=== RÉSUMÉ LOT 6 ===")
print(json.dumps(summary,ensure_ascii=False,indent=2))
