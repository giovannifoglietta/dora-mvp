from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from backend.db.database import get_db
from backend.models.schema import Booking, Client, Practitioner

router = APIRouter(prefix="/api")


@router.get("/state")
def get_state(db: Session = Depends(get_db)):
    """Snapshot of current DB state — used by the test UI."""
    practitioners = db.query(Practitioner).all()
    clients = db.query(Client).order_by(desc(Client.last_seen)).all()
    bookings = (
        db.query(Booking)
        .order_by(desc(Booking.created_at))
        .limit(20)
        .all()
    )

    client_by_id = {c.id: c for c in clients}

    return {
        "practitioners": [
            {"id": str(p.id), "name": p.name, "profession": p.profession}
            for p in practitioners
        ],
        "clients": [
            {
                "id": str(c.id),
                "name": c.name,
                "phone": c.phone,
                "last_seen": c.last_seen.isoformat() if c.last_seen else None,
            }
            for c in clients
        ],
        "bookings": [
            {
                "id": str(b.id),
                "client_phone": client_by_id[b.client_id].phone if b.client_id in client_by_id else None,
                "client_name": client_by_id[b.client_id].name if b.client_id in client_by_id else None,
                "service": b.service,
                "starts_at": b.starts_at.isoformat() if b.starts_at else None,
                "duration_minutes": b.duration_minutes,
                "status": b.status,
                "created_via": b.created_via,
            }
            for b in bookings
        ],
    }


@router.post("/reset")
def reset_test_data(db: Session = Depends(get_db)):
    """Wipe all clients & bookings (keep practitioners). For test UI use only."""
    db.query(Booking).delete()
    db.query(Client).delete()
    db.commit()
    return {"status": "reset"}
