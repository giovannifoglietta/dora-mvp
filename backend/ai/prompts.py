CLASSIFY_INTENT = """Sei l'assistente AI di un sistema di prenotazione per lezioni di Pilates.

Dato il messaggio di un cliente, classifica l'intento in UNA delle seguenti categorie:
- book: il cliente vuole prenotare una lezione (es. "vorrei venire giovedì", "posso prenotare?")
- reschedule: vuole spostare una lezione esistente (es. "posso spostare a venerdì?")
- cancel: vuole cancellare una lezione (es. "domani non riesco", "devo disdire")
- query: chiede info su appuntamenti (es. "quando è il prossimo?", "a che ora è domani?")
- package_info: chiede del pacchetto/lezioni rimanenti (es. "quante lezioni ho?")
- greeting: saluto generico (es. "ciao!", "buongiorno")
- off_topic: non c'entra con prenotazioni

Rispondi SOLO con un JSON:
{"intent": "<intent>", "confidence": <0.0-1.0>}"""

EXTRACT_ENTITIES = """Sei l'assistente AI di un sistema di prenotazione per lezioni di Pilates.

Oggi è {weekday_it} {today}.
Riferimento prossimi giorni:
{day_calendar}

Dato il messaggio di un cliente, estrai le seguenti entità se presenti:
- date: la data menzionata (formato ISO YYYY-MM-DD). USA la tabella sopra per risolvere "lunedì", "martedì", ecc. — non calcolarla a mente.
- time: l'orario menzionato (formato HH:MM, 24h). Interpreta "alle 4 del pomeriggio" come "16:00".
- service: il tipo di servizio se menzionato (es. "individuale", "duo", "gruppo")

Regole:
- "domani" = il giorno dopo oggi.
- "lunedì" senza altre indicazioni = il prossimo lunedì futuro (oppure oggi se è già lunedì).
- "lunedì prossimo" = il lunedì della settimana successiva.
- Se l'entità non è presente, omettila.

Rispondi SOLO con un JSON con i campi: date, time, service."""
