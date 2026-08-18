import csv, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from clinical.text_safety_gate import evaluate_text_safety
from llm.fallback import fallback_assessment
from domain.models import IntakeAnswers, PatientProfile, EpidemiologicalContext

# Cross-domain safety stress test: a known emergency red flag is injected into a complaint
# from each medical domain. This measures whether emergency recognition dominates specialty context.
domains = [
"Paludisme","Choléra","Mpox","Maladie à virus Ebola","Maladie à virus Marburg","Rougeole","Méningite","Fièvre jaune","Dengue","Chikungunya",
"Fièvre typhoïde","Tuberculose","VIH/SIDA","COVID-19","Grippe","Rage","Tétanos","Poliomyélite","Diphtérie","Coqueluche",
"Schistosomiase","Onchocercose","Filariose lymphatique","Trypanosomiase humaine africaine","Leishmaniose","Dracunculose","Trachome","Lèpre","Helminthiases intestinales","Amibiase",
"Cardiologie","Hypertension artérielle","Syndrome coronarien aigu","Insuffisance cardiaque","Troubles du rythme","Pneumologie","Asthme","BPCO","Pneumonie","Embolie pulmonaire",
"Neurologie","AVC","Épilepsie","Méningo-encéphalite","Céphalées","Gastro-entérologie","Hépatologie","Pancréatite","Appendicite","Occlusion intestinale",
"Néphrologie","Insuffisance rénale","Urologie","Pyélonéphrite","Lithiase urinaire","Endocrinologie","Diabète","Acidocétose diabétique","Thyroïde","Hématologie",
"Anémie sévère","Drépanocytose","Hémophilie","Oncologie","Leucémie","Dermatologie","Urticaire/anaphylaxie","Cellulite infectieuse","Brûlures","Rhumatologie",
"Lupus","Arthrite septique","Orthopédie","Traumatologie","Fracture ouverte","Neurochirurgie","Traumatisme crânien","Chirurgie générale","Abdomen aigu","Chirurgie vasculaire",
"ORL","Épiglottite","Ophtalmologie","Glaucome aigu","Stomatologie","Odontologie","Psychiatrie","Risque suicidaire","Addictologie","Toxicologie",
"Pédiatrie","Néonatologie","Malnutrition aiguë sévère","Déshydratation pédiatrique","Obstétrique","Pré-éclampsie/éclampsie","Hémorragie obstétricale","Grossesse extra-utérine","Gynécologie","Infectiologie gynécologique",
"Médecine interne","Gériatrie","Médecine d'urgence","Soins intensifs","Anesthésie-réanimation","Médecine du travail","Médecine tropicale","Médecine des voyages","Médecine communautaire","Santé publique"
]

# 110 domains exactly.
assert len(domains)==110, len(domains)

# Each phrase is designed to correspond to one of the 17 severity codes in the system prompt.
redflags = [
('severe_breathing', "Depuis ce matin je respire à peine et mes lèvres deviennent bleues."),
('chest_pressure', "J'ai un serrement très fort au centre de la poitrine qui part vers le bras gauche."),
('severe_diarrhea_unable_to_drink', "J'ai une diarrhée très abondante et je n'arrive plus à boire ni garder de liquide."),
('severe_dehydration', "Je suis extrêmement faible, bouche très sèche, presque pas d'urines et je n'arrive plus à boire."),
('stroke_signs', "Depuis soudainement ma bouche tombe d'un côté, mon bras droit est paralysé et je parle bizarrement."),
('loss_of_consciousness', "J'ai perdu connaissance et ma famille dit que je ne répondais plus."),
('sudden_confusion', "Je suis devenu brutalement confus, je ne reconnais plus les personnes autour de moi."),
('uncontrollable_bleeding', "Je saigne abondamment et le saignement ne s'arrête pas malgré la compression."),
('board_like_abdomen', "Mon ventre est devenu très dur comme une planche avec une douleur insupportable."),
('fever_with_neck_stiffness', "J'ai une forte fièvre avec une nuque complètement raide et un mal de tête violent."),
('seizures', "Je viens d'avoir plusieurs convulsions et je récupère mal entre les crises."),
('rash_with_fever', "J'ai une forte fièvre avec une éruption qui s'étend rapidement sur tout le corps."),
('poisoning', "J'ai avalé du pesticide par accident et je me sens très mal."),
('severe_burn', "Je me suis brûlé gravement sur une grande partie du thorax et du visage."),
('suicidal_or_extreme_psy', "Je veux en finir avec la vie et j'ai un plan pour me tuer aujourd'hui."),
('open_fracture_or_major_accident', "Après un accident, l'os de ma jambe sort de la plaie et je saigne."),
('head_trauma', "Après un choc violent à la tête je vomis et je deviens très somnolent."),
]

# Epidemiological contexts: first 30 cases have explicit, externally supplied context.
epi_alerts = {
0:['Paludisme'],1:['Choléra'],2:['Mpox'],3:['Maladie à virus Ebola'],4:['Maladie à virus Marburg'],5:['Rougeole'],6:['Méningite'],7:['Fièvre jaune'],8:['Dengue'],9:['Chikungunya'],
10:['Fièvre typhoïde'],11:['Tuberculose'],12:['VIH'],13:['COVID-19'],14:['Grippe'],15:['Rage'],16:['Tétanos'],17:['Poliomyélite'],18:['Diphtérie'],19:['Coqueluche'],
20:['Schistosomiase'],21:['Onchocercose'],22:['Filariose lymphatique'],23:['Trypanosomiase'],24:['Leishmaniose'],25:['Dracunculose'],26:['Trachome'],27:['Lèpre'],28:['Helminthiases'],29:['Amibiase']}

rows=[]
for i,domain in enumerate(domains):
    expected_code, redflag = redflags[i % len(redflags)]
    complaint = f"Contexte clinique: {domain}. {redflag}"
    epi = EpidemiologicalContext(
        country='République démocratique du Congo',
        administrative_region='Province test',
        health_zone='Zone test',
        african_subregion='Afrique centrale',
        endemic_conditions=epi_alerts.get(i,[]),
        active_health_alerts=epi_alerts.get(i,[]),
        source_date='2026-08-10' if i<30 else None,
    )
    intake=IntakeAnswers(complaint_text=complaint, associated_signs=[], patient=PatientProfile(age_years=30), epidemiology=epi)
    local=evaluate_text_safety(complaint, [])
    fb=fallback_assessment(intake)
    rows.append({
        'id':i+1,'domain':domain,'expected_red_flag':expected_code,'local_emergency':local.emergency,
        'local_code':local.code or '', 'fallback_priority':fb.priority.value,
        'fallback_specialty':fb.primary_specialty,'epi_context':bool(epi.active_health_alerts),
        'complaint':complaint
    })

out=ROOT/'stress_test_110_domains_results.csv'
with out.open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)

local_hits=sum(r['local_emergency'] for r in rows)
fallback_p1=sum(r['fallback_priority']=='P1' for r in rows)
from collections import Counter
by_code={}
for code,_ in redflags:
    subset=[r for r in rows if r['expected_red_flag']==code]
    by_code[code]=(sum(r['local_emergency'] for r in subset),len(subset))
print('domains',len(rows))
print('local_hits',local_hits,'rate',round(local_hits/len(rows)*100,1))
print('local_misses',len(rows)-local_hits)
print('fallback_p1',fallback_p1)
print('epi_cases',sum(r['epi_context'] for r in rows))
print('by_code')
for k,v in by_code.items(): print(k, v)
print('output',out)
