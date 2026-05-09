"""Tests for the deterministic fast-path parser."""
from datetime import date
import pytest
from backend.ai.rules import try_parse


SAT = date(2026, 5, 9)  # saturday


@pytest.mark.parametrize("text", ["ciao", "Ciao!", "buongiorno", "Buona sera", "salve", "ehi"])
def test_greetings(text):
    r = try_parse(text, SAT)
    assert r and r["intent"] == "greeting"


@pytest.mark.parametrize("text", [
    "quante lezioni mi restano?",
    "pacchetto?",
    "lezioni rimaste",
    "quante lezioni ho?",
])
def test_package_queries(text):
    r = try_parse(text, SAT)
    assert r and r["intent"] == "package_info"


@pytest.mark.parametrize("text", [
    "quando è il mio prossimo appuntamento?",
    "che giorno è la prossima lezione?",
])
def test_query_next(text):
    r = try_parse(text, SAT)
    assert r and r["intent"] == "query"


def test_book_with_date_and_time():
    r = try_parse("vorrei prenotare giovedì alle 10", SAT)
    assert r["intent"] == "book"
    assert r["date"] == "2026-05-14"  # next Thursday
    assert r["time"] == "10:00"


def test_book_relative_tomorrow():
    r = try_parse("prenotami domani alle 9", SAT)
    assert r["intent"] == "book"
    assert r["date"] == "2026-05-10"
    assert r["time"] == "09:00"


def test_book_lunedi_resolves_to_monday():
    r = try_parse("posso venire lunedì alle 14", SAT)
    assert r["intent"] == "book"
    assert r["date"] == "2026-05-11"  # next Monday
    assert r["time"] == "14:00"


def test_cancel_with_date():
    r = try_parse("cancella domani", SAT)
    assert r["intent"] == "cancel"
    assert r["date"] == "2026-05-10"


def test_cancel_inflected():
    r = try_parse("cancellami giovedì", SAT)
    assert r["intent"] == "cancel"


def test_disdici():
    r = try_parse("disdici la lezione di domani", SAT)
    assert r["intent"] == "cancel"
    assert r["date"] == "2026-05-10"


def test_reschedule():
    r = try_parse("sposta la lezione di domani alle 15", SAT)
    assert r["intent"] == "reschedule"
    assert r["date"] == "2026-05-10"
    assert r["time"] == "15:00"


def test_short_continuation_just_time():
    r = try_parse("alle 10", SAT)
    assert r["intent"] == "book"
    assert r["time"] == "10:00"


def test_short_continuation_just_date():
    r = try_parse("martedì", SAT)
    assert r["intent"] == "book"
    assert r["date"] == "2026-05-12"


def test_unknown_returns_none():
    assert try_parse("ho mal di schiena", SAT) is None
    assert try_parse("che tempo fa?", SAT) is None


def test_aiuto_falls_through():
    # "aiuto" is handled separately by orchestrator keyword shortcut, not by rules
    assert try_parse("aiuto", SAT) is None


def test_empty():
    assert try_parse("", SAT) is None


def test_dopodomani():
    r = try_parse("vorrei venire dopodomani alle 11", SAT)
    assert r is not None
    # 'venire' is part of "vorrei venire" → matches book pattern
    assert r["date"] == "2026-05-11"
    assert r["time"] == "11:00"


def test_lunedi_prossimo_jumps_a_week():
    # "lunedì prossimo" should resolve to NEXT week's Monday, not this coming one
    r = try_parse("vorrei prenotare lunedì prossimo alle 10", SAT)
    assert r["date"] == "2026-05-18"
