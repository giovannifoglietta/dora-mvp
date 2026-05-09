from datetime import date
from typing import Optional
from sqlalchemy.orm import Session
from backend.models.schema import Package, Client


def active_package(db: Session, client_id) -> Optional[Package]:
    """Return the oldest still-usable package for a client (FIFO)."""
    today = date.today()
    return (
        db.query(Package)
        .filter(
            Package.client_id == client_id,
            Package.used_sessions < Package.total_sessions,
        )
        .filter((Package.expiry_date == None) | (Package.expiry_date >= today))  # noqa: E711
        .order_by(Package.purchase_date.asc())
        .first()
    )


def sessions_remaining(pkg: Package) -> int:
    return max(0, pkg.total_sessions - pkg.used_sessions)


def create_package(
    db: Session,
    practitioner_id,
    client_id,
    total_sessions: int,
    expiry_date: Optional[date] = None,
    payment_status: str = "paid",
    notes: Optional[str] = None,
) -> Package:
    pkg = Package(
        practitioner_id=practitioner_id,
        client_id=client_id,
        total_sessions=total_sessions,
        used_sessions=0,
        purchase_date=date.today(),
        expiry_date=expiry_date,
        payment_status=payment_status,
        notes=notes,
    )
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return pkg


def list_packages(db: Session, practitioner_id):
    return (
        db.query(Package)
        .filter_by(practitioner_id=practitioner_id)
        .order_by(Package.purchase_date.desc())
        .all()
    )
