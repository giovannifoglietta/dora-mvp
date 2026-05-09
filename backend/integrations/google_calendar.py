"""Google Calendar sync.

Two ways to authenticate, in order of preference:
1. Per-practitioner OAuth (built via google_oauth.py): uses each practitioner's
   own Google account, bookings appear in their personal calendar of choice.
2. Service account fallback: a single shared calendar that you share with the
   service account email. Useful for testing / single-tenant deploys.

If neither is configured, every call here is a no-op so bookings still work locally.
"""
import base64
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from backend.config import settings
from backend.timezone import ROME_TZ
from backend.integrations import google_oauth

logger = logging.getLogger(__name__)

# Service-account fallback (lazily initialized)
_sa_service = None
_sa_disabled_reason: Optional[str] = None


def _get_sa_service():
    global _sa_service, _sa_disabled_reason
    if _sa_service is not None:
        return _sa_service
    if _sa_disabled_reason:
        return None

    if not settings.google_service_account_json or not settings.google_calendar_id:
        _sa_disabled_reason = "GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_CALENDAR_ID not set"
        return None

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        _sa_disabled_reason = "google-api-python-client not installed"
        return None

    try:
        raw = settings.google_service_account_json.strip()
        info = _parse_credentials(raw)
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        _sa_service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return _sa_service
    except Exception as e:
        logger.error(f"Service account init failed: {e}")
        _sa_disabled_reason = str(e)
        return None


def _parse_credentials(raw: str) -> dict:
    if not raw.lstrip().startswith("{"):
        try:
            decoded = base64.b64decode(raw, validate=True).decode("utf-8")
            return json.loads(decoded)
        except Exception:
            pass
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    repaired = raw.replace("\r\n", "\n").replace("\n", "\\n")
    info = json.loads(repaired)
    pk = info.get("private_key", "")
    if pk:
        pk = pk.replace("BEGIN  PRIVATE  KEY", "BEGIN PRIVATE KEY")
        pk = pk.replace("END  PRIVATE  KEY", "END PRIVATE KEY")
        pk = pk.replace("\\n", "\n")
        info["private_key"] = pk
    return info


def _resolve_target(practitioner) -> Tuple[Optional[object], Optional[str], str]:
    """Return (service, calendar_id, mode) for whichever auth method is live.
    mode is 'oauth' | 'service_account' | 'disabled'."""
    # Prefer practitioner OAuth
    if practitioner is not None and getattr(practitioner, "gcal_oauth_refresh_token", None):
        svc = google_oauth.build_calendar_service(practitioner.gcal_oauth_refresh_token)
        if svc:
            calendar_id = practitioner.gcal_oauth_calendar_id or "primary"
            return svc, calendar_id, "oauth"

    # Fallback: shared service account calendar
    sa = _get_sa_service()
    if sa:
        return sa, settings.google_calendar_id, "service_account"

    return None, None, "disabled"


def is_enabled(practitioner=None) -> bool:
    svc, _, mode = _resolve_target(practitioner)
    return svc is not None and mode != "disabled"


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


def create_event(booking, client, practitioner=None) -> Optional[str]:
    svc, calendar_id, mode = _resolve_target(practitioner)
    if not svc:
        return None
    try:
        event = svc.events().insert(
            calendarId=calendar_id,
            body=_event_payload(booking, client),
        ).execute()
        return event.get("id")
    except Exception as e:
        logger.error(f"gcal create_event failed ({mode}): {e}")
        return None


def update_event(event_id: str, booking, client, practitioner=None) -> bool:
    svc, calendar_id, mode = _resolve_target(practitioner)
    if not svc or not event_id:
        return False
    try:
        svc.events().patch(
            calendarId=calendar_id,
            eventId=event_id,
            body=_event_payload(booking, client),
        ).execute()
        return True
    except Exception as e:
        logger.error(f"gcal update_event failed ({mode}): {e}")
        return False


def delete_event(event_id: str, practitioner=None) -> bool:
    svc, calendar_id, mode = _resolve_target(practitioner)
    if not svc or not event_id:
        return False
    try:
        svc.events().delete(
            calendarId=calendar_id,
            eventId=event_id,
        ).execute()
        return True
    except Exception as e:
        if "410" in str(e):
            return True
        logger.error(f"gcal delete_event failed ({mode}): {e}")
        return False


def list_calendars_for_practitioner(practitioner) -> list:
    """List all calendars on the practitioner's connected Google account."""
    if not practitioner or not practitioner.gcal_oauth_refresh_token:
        return []
    svc = google_oauth.build_calendar_service(practitioner.gcal_oauth_refresh_token)
    if not svc:
        return []
    try:
        result = svc.calendarList().list().execute()
        items = result.get("items", [])
        return [
            {
                "id": c.get("id"),
                "summary": c.get("summary"),
                "primary": c.get("primary", False),
                "access_role": c.get("accessRole"),
            }
            for c in items
        ]
    except Exception as e:
        logger.error(f"list_calendars_for_practitioner failed: {e}")
        return []


# Backward-compatible alias for the existing diagnostic endpoint
def get_disabled_reason() -> Optional[str]:
    return _sa_disabled_reason


# Module-level attribute kept around so older diagnostic code keeps working
_disabled_reason = _sa_disabled_reason
