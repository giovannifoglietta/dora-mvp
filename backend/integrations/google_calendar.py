"""Google Calendar sync using a service account.

Setup (see README):
1. Create a GCP project + service account, download the JSON key.
2. Set env var GOOGLE_SERVICE_ACCOUNT_JSON to either:
   - the full JSON content directly, OR
   - base64-encoded JSON (recommended for Railway and other PaaS where
     multi-line values can be mangled). Use:
         python -c "import base64,sys;print(base64.b64encode(sys.stdin.read().encode()).decode())" < key.json
3. Set GOOGLE_CALENDAR_ID to the calendar's ID (e.g. abc...@group.calendar.google.com).
4. In Google Calendar, share that calendar with the service account email
   (`...@<project>.iam.gserviceaccount.com`) with "Make changes to events".

If either env var is missing, every function here is a no-op — bookings still work
locally without any Google integration.
"""
import base64
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from backend.config import settings
from backend.timezone import ROME_TZ

logger = logging.getLogger(__name__)

_service = None
_disabled_reason: Optional[str] = None


def _get_service():
    """Lazy build the Calendar service. Returns None and caches reason on failure."""
    global _service, _disabled_reason
    if _service is not None:
        return _service
    if _disabled_reason:
        return None

    if not settings.google_service_account_json or not settings.google_calendar_id:
        _disabled_reason = "GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_CALENDAR_ID not set"
        return None

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        _disabled_reason = "google-api-python-client not installed"
        return None

    try:
        raw = settings.google_service_account_json.strip()
        info = _parse_credentials(raw)
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        _service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return _service
    except Exception as e:
        logger.error(f"Google Calendar init failed: {e}")
        _disabled_reason = str(e)
        return None


def _parse_credentials(raw: str) -> dict:
    """Accept either base64-encoded JSON or raw JSON. Repair common
    Railway-style env-var mangling (literal newlines inside string values)."""
    # Try base64 first
    if not raw.lstrip().startswith("{"):
        try:
            decoded = base64.b64decode(raw, validate=True).decode("utf-8")
            return json.loads(decoded)
        except Exception:
            pass

    # Try direct JSON
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Last resort: repair literal newlines inside the value. Railway sometimes
    # turns escaped \n into real newlines, including inside the PEM body.
    repaired = raw.replace("\r\n", "\n").replace("\n", "\\n")
    info = json.loads(repaired)
    # Repair the private_key field if needed: collapse any whitespace inside
    # the BEGIN/END markers to single spaces.
    pk = info.get("private_key", "")
    if pk:
        # Normalize the BEGIN/END markers
        pk = pk.replace("BEGIN  PRIVATE  KEY", "BEGIN PRIVATE KEY")
        pk = pk.replace("END  PRIVATE  KEY", "END PRIVATE KEY")
        # Restore newlines
        pk = pk.replace("\\n", "\n")
        info["private_key"] = pk
    return info


def is_enabled() -> bool:
    return _get_service() is not None


def _event_payload(booking, client) -> dict:
    starts = booking.starts_at
    if starts.tzinfo is None:
        starts = starts.replace(tzinfo=ROME_TZ)
    ends = starts + timedelta(minutes=booking.duration_minutes or 55)
    title_name = client.full_name if client else "Cliente"
    return {
        "summary": f"{booking.service or 'Lezione'} — {title_name}",
        "description": (
            f"Cliente: {title_name}\n"
            f"Telefono: {client.phone if client else ''}\n"
            f"Servizio: {booking.service or 'Lezione'}\n"
            f"Prenotato via: {booking.created_via}\n"
            f"ID Dora: {booking.id}"
        ),
        "start": {"dateTime": starts.isoformat(), "timeZone": "Europe/Rome"},
        "end": {"dateTime": ends.isoformat(), "timeZone": "Europe/Rome"},
    }


def create_event(booking, client) -> Optional[str]:
    """Create a calendar event. Returns the event id, or None if disabled/failed."""
    svc = _get_service()
    if not svc:
        return None
    try:
        event = svc.events().insert(
            calendarId=settings.google_calendar_id,
            body=_event_payload(booking, client),
        ).execute()
        return event.get("id")
    except Exception as e:
        logger.error(f"gcal create_event failed: {e}")
        return None


def update_event(event_id: str, booking, client) -> bool:
    svc = _get_service()
    if not svc or not event_id:
        return False
    try:
        svc.events().patch(
            calendarId=settings.google_calendar_id,
            eventId=event_id,
            body=_event_payload(booking, client),
        ).execute()
        return True
    except Exception as e:
        logger.error(f"gcal update_event failed: {e}")
        return False


def delete_event(event_id: str) -> bool:
    svc = _get_service()
    if not svc or not event_id:
        return False
    try:
        svc.events().delete(
            calendarId=settings.google_calendar_id,
            eventId=event_id,
        ).execute()
        return True
    except Exception as e:
        # 410 Gone is fine (already deleted)
        if "410" in str(e):
            return True
        logger.error(f"gcal delete_event failed: {e}")
        return False
