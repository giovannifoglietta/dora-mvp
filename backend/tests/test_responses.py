"""Tests for response template module — verify key information appears in replies."""
from backend import responses


def test_greeting_contains_dora():
    assert "Dora" in responses.GREETING
    assert "Silvia" in responses.GREETING


def test_help_lists_capabilities():
    h = responses.HELP
    assert "Prenotare" in h
    assert "Spostare" in h or "spostare" in h
    assert "Cancellare" in h or "cancellare" in h
    assert "pacchetto" in h


def test_propose_booking_includes_when_and_service():
    msg = responses.propose_booking("giovedì 14 maggio alle 10:00", "Pilates Individuale")
    assert "giovedì 14 maggio" in msg
    assert "10:00" in msg
    assert "Pilates Individuale" in msg
    assert "confermi" in msg.lower()


def test_booking_confirmed_uses_first_name():
    msg = responses.booking_confirmed("Marco", "lunedì 11 maggio alle 09:00")
    assert "Marco" in msg
    assert "lunedì 11 maggio alle 09:00" in msg


def test_package_balance():
    msg = responses.package_balance(remaining=2, total=10, expiry_label=" (scade il 30/06/2026)")
    assert "2" in msg
    assert "10" in msg
    assert "30/06/2026" in msg


def test_no_active_package_uses_name():
    msg = responses.no_active_package("Anna")
    assert "Anna" in msg
    assert "Silvia" in msg


def test_low_balance_alert_mentions_count():
    assert "2" in responses.package_low_balance_alert(2)
    assert "1" in responses.package_low_balance_alert(1)


def test_thanks_back_with_name():
    assert "Marco" in responses.thanks_back("Marco")


def test_thanks_back_no_name():
    msg = responses.thanks_back(None)
    assert "Di nulla" in msg
    # No stray comma when name is missing
    assert "Di nulla," not in msg


def test_cancellation_confirmed_includes_when():
    msg = responses.cancellation_confirmed("giovedì 14 maggio alle 10:00")
    assert "giovedì 14 maggio alle 10:00" in msg


def test_slot_taken_with_alternatives_lists_them():
    alts = ["giovedì alle 11:00", "giovedì alle 14:00"]
    msg = responses.slot_taken_with_alternatives("giovedì alle 10:00", alts)
    assert "giovedì alle 10:00" in msg
    for a in alts:
        assert a in msg
