from __future__ import annotations

import argparse
import json

from app.logging_config import configure_logging
from domain.models import EpidemiologicalContext, IntakeAnswers, PatientProfile
from intake.base_questions import (
    ASSOCIATED_OPTIONS,
    CONSULT_OPTIONS,
    DURATION_OPTIONS,
    HISTORY_OPTIONS,
    IMMEDIATE_SEVERITY_SIGNS,
    normalize_sex,
)
from services.triage_service import TriageService


def yes_no(prompt: str) -> bool:
    accepted = {'o': True, 'oui': True, 'y': True, 'yes': True, 'n': False, 'non': False, 'no': False}
    while True:
        value = input(f'{prompt} (o/n) : ').strip().lower()
        if value in accepted:
            return accepted[value]
        print('Répondez par o ou n.')


def choose_one(title: str, options: list[str]) -> str:
    print(title)
    for index, option in enumerate(options, start=1):
        print(f'  {index}. {option}')
    while True:
        raw = input('Votre choix : ').strip()
        try:
            index = int(raw) - 1
            if index < 0:
                raise IndexError
            return options[index]
        except (ValueError, IndexError):
            print('Choix invalide.')


def choose_many(title: str, options: list[str]) -> list[str]:
    print(title)
    for index, option in enumerate(options, start=1):
        print(f'  {index}. {option}')
    while True:
        raw = input('Numéros séparés par des virgules : ').strip()
        if not raw:
            print('Sélectionnez au moins une option.')
            continue
        selected: list[str] = []
        try:
            for value in raw.split(','):
                index = int(value.strip()) - 1
                if index < 0:
                    raise IndexError
                option = options[index]
                if option not in selected:
                    selected.append(option)
        except (ValueError, IndexError):
            print('Choix invalide.')
            continue
        if len(selected) > 1 and any(item in {'Aucun', 'Aucun antécédent'} for item in selected):
            print("L'option « Aucun » ne peut pas être associée à une autre réponse.")
            continue
        return selected


def optional_float(prompt: str, minimum: float, maximum: float) -> float | None:
    while True:
        raw = input(prompt).strip().replace(',', '.')
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError:
            print('Entrez un nombre valide ou laissez vide.')
            continue
        if not minimum <= value <= maximum:
            print(f'La valeur doit être comprise entre {minimum} et {maximum}.')
            continue
        return value


def optional_int(prompt: str, minimum: int, maximum: int) -> int | None:
    while True:
        raw = input(prompt).strip()
        if not raw:
            return None
        try:
            value = int(raw)
        except ValueError:
            print('Entrez un nombre entier ou laissez vide.')
            continue
        if not minimum <= value <= maximum:
            print(f'La valeur doit être comprise entre {minimum} et {maximum}.')
            continue
        return value


def read_sex() -> str:
    while True:
        sex = normalize_sex(input('Sexe (Homme/Femme) : '))
        if sex != 'unknown':
            return sex
        print('Entrez Homme, Femme, H, F, masculin ou féminin.')


def display_patient_result(result) -> None:
    patient = result.patient_result
    print('\n' + '=' * 90)
    print('RÉSULTAT')
    print('=' * 90)
    print(f'Priorité       : {patient.priority.value}')
    print(f'Niveau         : {patient.urgency_label}')
    print(f'Orientation    : {patient.orientation}')
    print(f'Spécialité     : {patient.specialty}')
    print('\nHypothèses cliniques possibles à confirmer par un médecin :')
    if patient.priority.value == 'P1':
        print('  - Non affichées en situation d’urgence immédiate.')
    elif patient.possible_conditions:
        for condition in patient.possible_conditions[:3]:
            print(f'  - {condition}')
    else:
        print('  - Aucune hypothèse suffisamment fiable avec les informations disponibles.')
    print(f'\n{patient.diagnostic_disclaimer}')
    print('\nSynthèse :')
    print(patient.summary)
    if patient.reasons:
        print('\nÉléments pris en compte :')
        for item in patient.reasons:
            print(f'  - {item}')
    if patient.what_to_do_now:
        print('\nQue faire maintenant :')
        for item in patient.what_to_do_now:
            print(f'  - {item}')
    if patient.warning_signs:
        print('\nConsultez immédiatement si :')
        for item in patient.warning_signs:
            print(f'  - {item}')
    print(f'\n{patient.disclaimer}')


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description='AlloDocteur V6.2 Africa Context')
    parser.add_argument('--json', action='store_true', help='Afficher la réponse publique en JSON.')
    parser.add_argument('--technical', action='store_true', help='Afficher également le résultat technique complet.')
    args = parser.parse_args()

    print('=' * 90)
    print('ALLODOCTEUR V6.2 — RAISONNEMENT CLINIQUE + CONTEXTE AFRICAIN')
    print('Pré-triage et orientation uniquement, pas diagnostic.')
    print('Aucune base de règles et aucune question complémentaire ne sont utilisées.')
    print('=' * 90)

    complaint = input('1. Décrivez librement la plainte du patient : ').strip()
    while len(complaint) < 3:
        complaint = input('Décrivez la plainte avec au moins quelques mots : ').strip()

    duration = choose_one('\n2. Depuis quand avez-vous ce problème ?', DURATION_OPTIONS)
    associated = choose_many('\n3. Signes associés', ASSOCIATED_OPTIONS)
    consulted = choose_one('\n4. Avez-vous déjà consulté ?', CONSULT_OPTIONS)
    attachment = yes_no('5. Une photo ou un document est-il disponible ?')
    history = choose_many('\n6. Antécédents médicaux', HISTORY_OPTIONS)

    print('\n7. Profil du patient')
    date_of_birth = input('Date de naissance (JJ/MM/AAAA) : ').strip() or None
    sex = read_sex()
    pregnant = yes_no('La patiente est-elle enceinte ?') if sex == 'female' else False
    pregnancy_weeks = optional_int('Nombre de semaines de grossesse (vide si inconnu) : ', 0, 45) if pregnant else None
    country = input('Pays : ').strip() or 'République démocratique du Congo'
    province = input('Province / région : ').strip() or None
    health_zone = input('Ville, district ou zone de santé (optionnel) : ').strip() or None
    environment = choose_one(
        'Milieu de résidence',
        ['Urbain', 'Périurbain', 'Rural', 'Zone forestière', 'Zone minière', 'Camp de déplacés/réfugiés', 'Autre'],
    )
    season = input('Saison ou période climatique (optionnel) : ').strip() or None
    travel_raw = input('Voyages récents, pays/régions séparés par des virgules (optionnel) : ').strip()
    recent_travel = [item.strip() for item in travel_raw.split(',') if item.strip()]

    print('\n8. Mesures disponibles')
    weight = optional_float('Poids en kg (optionnel) : ', 1, 350)
    height = optional_float('Taille en mètre (optionnel) : ', 0.35, 2.60)
    temperature = optional_float('Température en °C (optionnel) : ', 30, 45)

    print('\nSignes de sévérité immédiate')
    severity_answers = {code: yes_no(label) for code, label in IMMEDIATE_SEVERITY_SIGNS.items()}

    intake = IntakeAnswers(
        complaint_text=complaint,
        duration=duration,
        associated_signs=associated,
        prior_consultation=consulted,
        attachment_present=attachment,
        medical_history=history,
        patient=PatientProfile(
            date_of_birth=date_of_birth,
            sex=sex,
            pregnant=pregnant,
            pregnancy_weeks=pregnancy_weeks,
            province=province,
            weight_kg=weight,
            height_m=height,
            temperature_c=temperature,
        ),
        severity_answers=severity_answers,
        epidemiology=EpidemiologicalContext(
            country=country,
            administrative_region=province,
            health_zone=health_zone,
            environment=environment,
            season=season,
            recent_travel=recent_travel,
        ),
    )

    import time
    print('\nAnalyse en cours...', flush=True)
    started = time.perf_counter()
    decision = TriageService().triage(intake)
    elapsed = time.perf_counter() - started
    print(f'Analyse terminée en {elapsed:.1f} seconde(s).', flush=True)
    public = decision.to_public_response()

    if args.json:
        print(json.dumps(public.model_dump(mode='json'), ensure_ascii=False, indent=2))
    else:
        display_patient_result(public)
        api_json = {
            'priority_code': public.patient_result.priority.value,
            'urgency_label': public.patient_result.urgency_label,
            'orientation': public.patient_result.orientation,
            'specialty': public.patient_result.specialty,
            'possible_conditions': public.patient_result.possible_conditions,
            'message': public.patient_result.summary,
            'diagnostic_disclaimer': public.patient_result.diagnostic_disclaimer,
        }
        print('\n' + '=' * 90)
        print('RÉPONSE JSON API')
        print('=' * 90)
        print(json.dumps(api_json, ensure_ascii=False, indent=2))

    if args.technical:
        print('\n' + '=' * 90)
        print('RÉSULTAT TECHNIQUE — USAGE INTERNE')
        print(json.dumps(decision.model_dump(mode='json'), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
