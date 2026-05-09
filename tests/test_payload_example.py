import requests

API_URL = "http://localhost:8000/triage"
API_KEY = "test_key"

payload = {
    "complaint_text": "j ai mal au ventre et un peu de fievre",
    "duration_choice": "1_3_days",
    "associated_signs": ["Fièvre"],
    "medical_history": [],
    "date_of_birth": "22/08/2000",
    "sex": "Homme",
    "province": "Kinshasa",
    "immediate_red_flags": {}
}

r = requests.post(API_URL, headers={"X-API-Key": API_KEY}, json=payload, timeout=30)
print(r.status_code)
print(r.json())
