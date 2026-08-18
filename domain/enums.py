from enum import Enum

class Priority(str, Enum):
    P1 = 'P1'
    P2 = 'P2'
    P3 = 'P3'
    P4 = 'P4'

PRIORITY_RANK = {Priority.P4: 1, Priority.P3: 2, Priority.P2: 3, Priority.P1: 4}
PRIORITY_META = {
    Priority.P1: ('ROUGE', 'Urgence vitale', 'Urgences / hôpital le plus proche'),
    Priority.P2: ('ORANGE', 'Consultation modérée prioritaire', 'Consultation médicale prioritaire'),
    Priority.P3: ('JAUNE', 'Consultation générale', 'Médecin généraliste'),
    Priority.P4: ('VERT', 'Consultation programmée', 'Médecin généraliste'),
}
