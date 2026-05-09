"""Project-wide timezone constants. Use Europe/Rome everywhere we deal with
practitioner-facing dates and times."""
try:
    from zoneinfo import ZoneInfo
except ImportError:  # py < 3.9
    from backports.zoneinfo import ZoneInfo  # type: ignore

ROME_TZ = ZoneInfo("Europe/Rome")
