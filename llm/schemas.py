"""Contrat JSON strict AlloDocteur V6.4 Clinical & Epidemiological Safety."""

SEVERITY_CODES = [
    'severe_breathing','chest_pressure','severe_diarrhea_unable_to_drink','severe_dehydration',
    'stroke_signs','loss_of_consciousness','sudden_confusion','uncontrollable_bleeding',
    'board_like_abdomen','fever_with_neck_stiffness','seizures','rash_with_fever','poisoning',
    'severe_burn','suicidal_or_extreme_psy','open_fracture_or_major_accident','head_trauma',
]

V64_ASSESSMENT_SCHEMA = {
    'type':'object',
    'properties':{
        'clinical_summary':{'type':'string'},
        'priority':{'type':'string','enum':['P1','P2','P3','P4']},
        'primary_specialty':{'type':'string'},
        'possible_conditions':{'type':'array','items':{'type':'string'},'maxItems':3},
        'reasons':{'type':'array','items':{'type':'string'},'maxItems':5},
        'what_to_do_now':{'type':'array','items':{'type':'string'},'maxItems':4},
        'worsening_signs':{'type':'array','items':{'type':'string'},'maxItems':5},
        'detected_severity_signs':{'type':'array','items':{'type':'string','enum':SEVERITY_CODES},'maxItems':17},
        'severity_evidence':{'type':'array','items':{'type':'string'},'maxItems':6},
        'contradictions':{'type':'array','items':{'type':'string'},'maxItems':6},
        'uncertainty':{'type':'string','enum':['low','moderate','high']},
        'requires_human_review':{'type':'boolean'},
        'epidemiology_risk_notes':{'type':'array','items':{'type':'string'},'maxItems':4},
        'infection_control_precautions':{'type':'array','items':{'type':'string'},'maxItems':4},
    },
    'required':['clinical_summary','priority','primary_specialty','possible_conditions','reasons',
                'what_to_do_now','worsening_signs','detected_severity_signs','severity_evidence',
                'contradictions','uncertainty','requires_human_review','epidemiology_risk_notes',
                'infection_control_precautions'],
    'additionalProperties':False,
}
V63_ASSESSMENT_SCHEMA = V64_ASSESSMENT_SCHEMA
V611_ASSESSMENT_SCHEMA = V64_ASSESSMENT_SCHEMA
V61_ASSESSMENT_SCHEMA = V64_ASSESSMENT_SCHEMA
V6_ASSESSMENT_SCHEMA = V64_ASSESSMENT_SCHEMA
