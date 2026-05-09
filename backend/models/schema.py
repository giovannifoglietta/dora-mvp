import uuid
from sqlalchemy import Column, String, Integer, Boolean, Float, Text, ForeignKey, DateTime, Date
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from backend.db.database import Base


class Practitioner(Base):
    __tablename__ = "practitioners"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    profession = Column(String(100))
    working_hours = Column(JSONB, nullable=False)
    break_minutes = Column(Integer, default=5)
    services = Column(JSONB, nullable=False)
    timezone = Column(String(50), default="Europe/Rome")
    whatsapp_number = Column(String(20))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    gcal_oauth_refresh_token = Column(Text)
    gcal_oauth_email = Column(String(255))
    gcal_oauth_calendar_id = Column(String(255))


class Client(Base):
    __tablename__ = "clients"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    practitioner_id = Column(UUID(as_uuid=True), ForeignKey("practitioners.id", ondelete="CASCADE"))
    name = Column(String(100), nullable=False)  # legacy / display fallback
    first_name = Column(String(60))
    last_name = Column(String(60))
    phone = Column(String(20), nullable=False, unique=True)
    notes = Column(Text)
    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now())

    @property
    def full_name(self) -> str:
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.name or self.phone


class Booking(Base):
    __tablename__ = "bookings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    practitioner_id = Column(UUID(as_uuid=True), ForeignKey("practitioners.id", ondelete="CASCADE"))
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"))
    service = Column(String(100))
    starts_at = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    status = Column(String(20), default="confirmed")
    reminder_sent = Column(Boolean, default=False)
    created_via = Column(String(20), default="whatsapp")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    cancelled_at = Column(DateTime(timezone=True))
    gcal_event_id = Column(String(255))


class Package(Base):
    __tablename__ = "packages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    practitioner_id = Column(UUID(as_uuid=True), ForeignKey("practitioners.id", ondelete="CASCADE"))
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"))
    total_sessions = Column(Integer, nullable=False)
    used_sessions = Column(Integer, default=0)
    purchase_date = Column(Date, server_default=func.current_date())
    expiry_date = Column(Date)
    payment_status = Column(String(20), default="paid")
    notes = Column(Text)


class TimeBlock(Base):
    __tablename__ = "time_blocks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    practitioner_id = Column(UUID(as_uuid=True), ForeignKey("practitioners.id", ondelete="CASCADE"))
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    reason = Column(String(200))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"))
    direction = Column(String(10), nullable=False)
    body = Column(Text, nullable=False)
    intent = Column(String(30))
    entities = Column(JSONB)
    confidence = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
