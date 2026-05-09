"""User-facing reply templates.

All Italian copy lives here so we can tune tone in one place. Style guide:
- Warm and brief; one sentence when possible
- Use the client's first name when we know it
- Avoid over-explaining; the user knows what they asked
"""
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------

NAME_PROMPT = "Ciao! Sono Dora, l'assistente di Silvia. Come posso chiamarti?"
NAME_RETRY = "Non ho capito il tuo nome. Come ti chiami?"


def name_acknowledged(first_name: str) -> str:
    return f"Piacere {first_name}!"


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------

GREETING = "Ciao! Sono Dora, l'assistente di Silvia. Vuoi prenotare una lezione?"
NO_PRACTITIONER = "Configurazione mancante. Contatta Silvia."
HELP = (
    "Posso aiutarti a:\n"
    "• Prenotare una lezione (es. 'giovedì alle 10')\n"
    "• Spostare o cancellare una lezione\n"
    "• Dirti quando è il tuo prossimo appuntamento\n"
    "• Vedere quante lezioni hai nel pacchetto\n"
    "Cosa vuoi fare?"
)


def thanks_back(first_name: Optional[str] = None) -> str:
    name = f", {first_name}" if first_name else ""
    return f"Di nulla{name}! Se ti serve altro, scrivimi pure."


FALLBACK_QUESTION = (
    "Su questo non saprei risponderti. Posso aiutarti con prenotazioni, "
    "spostamenti o cancellazioni. Vuoi fare una di queste cose?"
)
FALLBACK_GENERIC = "Non sono sicura di aver capito. Vuoi prenotare, spostare o cancellare una lezione?"

NEGATION_OK = "Ok, nessun problema! Fammi sapere quando vuoi riprenotare."


# ---------------------------------------------------------------------------
# Booking — propose / confirm
# ---------------------------------------------------------------------------

def propose_booking(when_label: str, service: str) -> str:
    return f"Ti prenoto per {when_label} ({service}) — confermi?"


def booking_confirmed(first_name: str, when_label: str) -> str:
    return f"Perfetto {first_name}! Confermata per {when_label}. A presto!"


def slot_taken_with_alternatives(when_label: str, alternatives: Iterable[str]) -> str:
    alts = ", ".join(alternatives)
    return f"Mi spiace, {when_label} è già occupato. Ho disponibile: {alts}"


def slot_unavailable(when_label: str) -> str:
    return f"Mi spiace, {when_label} non è disponibile."


def slot_taken_meanwhile(alternatives: Iterable[str]) -> str:
    alts = list(alternatives)
    if not alts:
        return "Mi spiace, lo slot non è più disponibile. Vuoi un altro giorno?"
    return ("Mi spiace, qualcuno ha appena preso quello slot. Ho ancora libero: "
            + ", ".join(alts))


# ---------------------------------------------------------------------------
# Booking — collecting date/time
# ---------------------------------------------------------------------------

ASK_WHEN = "Per quando vorresti prenotare? (es. 'giovedì alle 10')"


def day_full(day_name: str, alternatives: Iterable[str]) -> str:
    return f"{day_name} è pieno. Ho liberi: " + ", ".join(alternatives)


def day_no_availability() -> str:
    return "Quel giorno non ho disponibilità. Vuoi un altro giorno?"


def day_options(day_name: str, slots_label: str) -> str:
    return f"Per {day_name} ho disponibile: {slots_label}. Quale preferisci?"


# ---------------------------------------------------------------------------
# Cancel / reschedule
# ---------------------------------------------------------------------------

NO_BOOKINGS_TO_CANCEL = "Non hai lezioni da cancellare."
NO_BOOKINGS_TO_RESCHEDULE = "Non hai lezioni da spostare. Vuoi prenotarne una?"


def which_to_cancel(listing: str) -> str:
    return f"Quale lezione vuoi cancellare? Hai: {listing}"


def cancellation_confirmed(when_label: str) -> str:
    return f"Ho cancellato la lezione di {when_label}. Vuoi prenotare un altro giorno?"


def reschedule_confirmed(when_label: str) -> str:
    return f"Fatto! Lezione spostata a {when_label}."


def reschedule_prompt(current_when_label: str) -> str:
    return f"Hai la lezione {current_when_label}. Quando vorresti spostarla?"


# ---------------------------------------------------------------------------
# Query / package
# ---------------------------------------------------------------------------

def next_appointment(when_label: str) -> str:
    return f"La tua prossima lezione è {when_label}."


NO_NEXT_APPOINTMENT = "Non hai lezioni in programma. Vuoi prenotarne una?"


def package_balance(remaining: int, total: int, expiry_label: str = "") -> str:
    return f"Hai {remaining} lezioni rimanenti su {total}{expiry_label}."


def no_active_package(first_name: str) -> str:
    return f"{first_name}, non risulta nessun pacchetto attivo. Vuoi parlarne con Silvia?"


PACKAGE_LAST_LESSON_ALERT = "\n\n⚠️ Era l'ultima lezione del tuo pacchetto. Parla con Silvia per rinnovarlo."


def package_low_balance_alert(remaining: int) -> str:
    return f"\n\nP.S. Ti restano {remaining} lezioni del pacchetto."


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def booking_error(detail: str) -> str:
    return f"Errore: {detail}"
