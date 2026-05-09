"""Seed the database with Silvia's practitioner record. Idempotent.

Usage: python -m backend.seed
"""
from backend.db.database import SessionLocal
from backend.models.schema import Practitioner

SILVIA_DATA = {
    "name": "Silvia",
    "phone": "+390000000000",  # placeholder until SIM is provisioned
    "profession": "Insegnante di Pilates",
    "working_hours": {
        "mon": [{"start": "08:00", "end": "13:00"}, {"start": "14:00", "end": "19:00"}],
        "tue": [{"start": "08:00", "end": "13:00"}, {"start": "14:00", "end": "19:00"}],
        "wed": [{"start": "08:00", "end": "13:00"}, {"start": "14:00", "end": "19:00"}],
        "thu": [{"start": "08:00", "end": "13:00"}, {"start": "14:00", "end": "19:00"}],
        "fri": [{"start": "08:00", "end": "13:00"}, {"start": "14:00", "end": "17:00"}],
        "sat": [{"start": "09:00", "end": "13:00"}],
    },
    "break_minutes": 5,
    "services": [
        {"name": "Pilates Individuale", "duration": 55, "price": 50},
        {"name": "Pilates Duo", "duration": 55, "price": 35},
        {"name": "Pilates Gruppo", "duration": 60, "price": 20},
    ],
    "timezone": "Europe/Rome",
}


def seed():
    db = SessionLocal()
    try:
        existing = db.query(Practitioner).filter_by(name="Silvia").first()
        if existing:
            print(f"Silvia already exists (id={existing.id}). Updating fields.")
            for key, value in SILVIA_DATA.items():
                setattr(existing, key, value)
        else:
            p = Practitioner(**SILVIA_DATA)
            db.add(p)
            print("Created practitioner Silvia.")
        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
