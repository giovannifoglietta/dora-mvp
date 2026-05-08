# Dora MVP — Piano Completo

## Obiettivo
Costruire un assistente AI WhatsApp-native che gestisce l'agenda di Silvia (insegnante di Pilates), permettendo ai suoi clienti di prenotare, spostare e cancellare lezioni via messaggio.

---

## Prima utente: Silvia

| Info | Dettaglio |
|------|-----------|
| Professione | Insegnante di Pilates |
| Problema | Gestisce prenotazioni via WhatsApp personale + agenda carta/telefono |
| Clienti stimati | 15-30 attivi |
| Sessioni/giorno | 6-8 |
| Servizi (da confermare) | Individuale, duo, piccolo gruppo |
| Orari (da confermare) | Da definire con lei |

---

## Architettura del sistema

```
Cliente (WhatsApp) 
    → 360dialog (BSP) 
        → Webhook (nostro backend FastAPI) 
            → AI Pipeline (Claude Haiku/Sonnet) 
            → Business Logic (calendario, booking, pacchetti) 
            → PostgreSQL (dati) 
        → Risposta al cliente via WhatsApp
        
Silvia (browser) 
    → Dashboard web (Next.js) 
        → Stessa PostgreSQL
```

---

## Account e servizi da creare

### Tabella completa

| # | Servizio | A cosa serve | Chi lo crea | Costo | Quando serve |
|---|----------|-------------|-------------|-------|--------------|
| 1 | **GitHub** (giovannifoglietta) | Repo codice + version control | ✅ Fatto | Gratis | Subito |
| 2 | **GitHub repo** `dora-mvp` | Progetto privato | Giovanni su github.com/new | Gratis | Subito |
| 3 | **Personal Access Token GitHub** | Push codice da terminale | Giovanni su GitHub Settings | Gratis | Subito |
| 4 | **Railway.app** | Hosting backend (EU) + cron jobs | Giovanni (signup con GitHub) | ~€5/mo | Settimana 1 |
| 5 | **Supabase** | PostgreSQL managed (EU) | Giovanni su supabase.com | Gratis (free tier) | Settimana 2 |
| 6 | **Anthropic API** | Claude Haiku per NLU | Giovanni su console.anthropic.com | ~€3-5/mo | Settimana 2 |
| 7 | **360dialog** | BSP per WhatsApp Business API | Giovanni su 360dialog.com | Costo per conversazione | Settimana 3 |
| 8 | **Meta Business Account** | Richiesto da 360dialog per WhatsApp | Giovanni su business.facebook.com | Gratis | Settimana 3 |
| 9 | **SIM dedicata** | Numero WhatsApp per Dora/Silvia | Giovanni (Iliad/ho.) | ~€5/mo | Settimana 3 |
| 10 | **Vercel** | Hosting dashboard web | Giovanni (signup con GitHub) | Gratis (free tier) | Settimana 5 |
| 11 | **Dominio** (opzionale MVP) | URL dashboard (es. app.usedora.it) | Giovanni su qualsiasi registrar | ~€10/anno | Settimana 5 |

---

## Struttura del progetto

```
dora-mvp/
├── README.md
├── PIANO_MVP.md
├── .env.example              # Template variabili d'ambiente
├── .gitignore
│
├── backend/
│   ├── main.py               # FastAPI app, entry point
│   ├── config.py             # Settings, env vars
│   ├── webhooks.py           # Endpoint ricezione messaggi WhatsApp
│   ├── whatsapp.py           # Client per invio messaggi via 360dialog
│   │
│   ├── ai/
│   │   ├── classifier.py    # Intent detection (book/reschedule/cancel/query)
│   │   ├── extractor.py     # Entity extraction (data, ora, servizio)
│   │   ├── context.py       # Gestione stato conversazione
│   │   └── prompts.py       # System prompts (italiano)
│   │
│   ├── logic/
│   │   ├── availability.py  # Verifica slot liberi
│   │   ├── booking.py       # CRUD prenotazioni
│   │   ├── packages.py      # Tracking pacchetti prepagati
│   │   └── reminders.py     # Scheduler reminder 24h
│   │
│   ├── models/
│   │   └── schema.py        # SQLAlchemy / Pydantic models
│   │
│   ├── db/
│   │   ├── database.py      # Connessione PostgreSQL
│   │   └── migrations/      # Alembic migrations
│   │
│   └── tests/
│       ├── test_classifier.py
│       ├── test_availability.py
│       └── test_booking.py
│
├── dashboard/
│   ├── package.json
│   ├── app/
│   │   ├── page.tsx          # Home → agenda settimanale
│   │   ├── clients/
│   │   │   └── page.tsx      # Lista clienti + pacchetti
│   │   └── settings/
│   │       └── page.tsx      # Orari, servizi, config
│   └── components/
│       ├── Calendar.tsx
│       ├── BookingCard.tsx
│       └── ClientList.tsx
│
└── docs/
    ├── onboarding-silvia.md  # Checklist onboarding
    ├── whatsapp-templates.md # Template messaggi per Meta approval
    └── conversation-flows.md # Flussi conversazione documentati
```

---

## Piano di build — Settimana per settimana

---

### SETTIMANA 1: Fondamenta (Giorni 1-7)

#### Obiettivo: Repo funzionante + backend scheletro deployato

**Giorno 1-2: Setup progetto**
- [ ] Creare repo `dora-mvp` su GitHub (privato)
- [ ] Generare Personal Access Token
- [ ] Creare struttura cartelle in locale
- [ ] Inizializzare git, pushare su GitHub
- [ ] Creare `requirements.txt` con dipendenze Python iniziali:
  ```
  fastapi
  uvicorn
  httpx
  pydantic
  python-dotenv
  ```
- [ ] Creare `.env.example` con tutte le variabili necessarie
- [ ] Creare `.gitignore` (Python + Node + .env)

**Giorno 3-4: Backend scheletro**
- [ ] `main.py`: FastAPI app con health check endpoint (`GET /` → "Dora is alive")
- [ ] `config.py`: carica variabili da `.env`
- [ ] `webhooks.py`: endpoint `GET /webhook` (verifica token) e `POST /webhook` (ricevi payload)
- [ ] `whatsapp.py`: funzione `send_message(phone, text)` (stub per ora)
- [ ] Test locale: `uvicorn main:app --reload` funziona

**Giorno 5-6: Deploy su Railway**
- [ ] Creare account Railway (signup con GitHub)
- [ ] Collegare repo `dora-mvp`
- [ ] Configurare: Python buildpack, variabili d'ambiente
- [ ] Creare `Procfile`: `web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- [ ] Verificare: `https://dora-mvp-xxx.railway.app/` → "Dora is alive"

**Giorno 7: Test webhook con tool esterno**
- [ ] Usare ngrok (locale) o l'URL Railway per testare il webhook
- [ ] Simulare un payload WhatsApp con curl/Postman
- [ ] Verificare che il backend logga il messaggio ricevuto

**Deliverable settimana 1:** Backend deployato che riceve richieste HTTP e risponde.

---

### SETTIMANA 2: AI Pipeline (Giorni 8-14)

#### Obiettivo: Il sistema capisce messaggi in italiano e classifica intenti

**Giorno 8-9: Anthropic API setup**
- [ ] Creare account su console.anthropic.com
- [ ] Generare API key
- [ ] Aggiungere `anthropic` a requirements.txt
- [ ] Impostare spending limit €20/mo
- [ ] Test: script Python che chiama Haiku e riceve risposta

**Giorno 10-11: Intent Classifier**
- [ ] `ai/prompts.py`: System prompt per classificazione intent
  ```
  Intenti supportati:
  - book: il cliente vuole prenotare (es. "vorrei venire giovedì")
  - reschedule: vuole spostare (es. "posso spostare a venerdì?")
  - cancel: vuole cancellare (es. "domani non riesco")
  - query: chiede info (es. "quando è il prossimo?")
  - package_info: chiede del pacchetto (es. "quante lezioni ho?")
  - greeting: saluto generico (es. "ciao!")
  - off_topic: non c'entra con prenotazioni
  ```
- [ ] `ai/classifier.py`: funzione `classify_intent(message) → intent, confidence`
- [ ] Test con 30+ messaggi di esempio in italiano
- [ ] Misurare accuratezza (target: >90% su messaggi chiari)

**Giorno 12-13: Entity Extraction**
- [ ] `ai/extractor.py`: funzione `extract_entities(message, intent) → {date, time, service}`
- [ ] Gestire:
  - Date esplicite: "giovedì 15 maggio alle 10"
  - Date relative: "domani", "la prossima settimana", "lunedì"
  - Orari: "alle 4", "alle 16", "nel pomeriggio"
  - Servizi: "lezione", "pilates", "individuale"
- [ ] Regex fallback per date/orari ovvie (non sempre servire l'LLM)
- [ ] Test con 30+ messaggi di esempio

**Giorno 14: Conversation Context**
- [ ] `ai/context.py`: gestione stato conversazione per cliente
  - Cosa ha chiesto prima?
  - Siamo in un flusso multi-turno? (es. "giovedì" → "a che ora?" → "le 10")
  - Ultimo intent, ultime entità estratte
- [ ] Storage: Redis (Railway addon) o semplice dict in-memory per MVP
- [ ] TTL: conversazione scade dopo 30 min di inattività

**Deliverable settimana 2:** Dato un messaggio WhatsApp in italiano, il sistema restituisce intent + entità corretti nel 90%+ dei casi chiari.

---

### SETTIMANA 3: WhatsApp Integration + Database (Giorni 15-21)

#### Obiettivo: Messaggi reali da WhatsApp gestiti dal sistema. Database con schema completo.

**Giorno 15-16: Database setup**
- [ ] Creare progetto Supabase (regione eu-west)
- [ ] Ottenere connection string PostgreSQL
- [ ] Definire schema SQL:

```sql
-- Practitioners
CREATE TABLE practitioners (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    profession VARCHAR(100),
    working_hours JSONB NOT NULL,
    -- es: {"mon": [{"start": "08:00", "end": "13:00"}, {"start": "14:00", "end": "19:00"}], ...}
    break_minutes INT DEFAULT 5,
    services JSONB NOT NULL,
    -- es: [{"name": "Pilates Individuale", "duration": 55}, {"name": "Pilates Duo", "duration": 55}]
    timezone VARCHAR(50) DEFAULT 'Europe/Rome',
    whatsapp_number VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Clients
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    practitioner_id UUID REFERENCES practitioners(id),
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL UNIQUE,
    notes TEXT,
    first_seen TIMESTAMP DEFAULT NOW(),
    last_seen TIMESTAMP DEFAULT NOW()
);

-- Bookings
CREATE TABLE bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    practitioner_id UUID REFERENCES practitioners(id),
    client_id UUID REFERENCES clients(id),
    service VARCHAR(100),
    starts_at TIMESTAMP NOT NULL,
    duration_minutes INT NOT NULL,
    status VARCHAR(20) DEFAULT 'confirmed',
    -- confirmed, cancelled, completed, no_show
    reminder_sent BOOLEAN DEFAULT FALSE,
    created_via VARCHAR(20) DEFAULT 'whatsapp',
    -- whatsapp, dashboard, manual
    created_at TIMESTAMP DEFAULT NOW(),
    cancelled_at TIMESTAMP
);

-- Packages
CREATE TABLE packages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    practitioner_id UUID REFERENCES practitioners(id),
    client_id UUID REFERENCES clients(id),
    total_sessions INT NOT NULL,
    used_sessions INT DEFAULT 0,
    purchase_date DATE DEFAULT CURRENT_DATE,
    expiry_date DATE,
    payment_status VARCHAR(20) DEFAULT 'paid',
    -- paid, pending, partial
    notes TEXT
);

-- Conversation log (per debugging e miglioramenti)
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id),
    direction VARCHAR(10) NOT NULL, -- inbound, outbound
    body TEXT NOT NULL,
    intent VARCHAR(30),
    entities JSONB,
    confidence FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

- [ ] Eseguire migration su Supabase
- [ ] `db/database.py`: connessione + session management (SQLAlchemy o asyncpg)
- [ ] `models/schema.py`: Pydantic models per validazione

**Giorno 17-18: 360dialog + WhatsApp setup**
- [ ] Creare account 360dialog
- [ ] Creare Meta Business Account (se non esiste già)
- [ ] Collegare Meta Business a 360dialog
- [ ] Registrare la SIM dedicata come numero WhatsApp Business
- [ ] Ottenere API key 360dialog
- [ ] Configurare webhook URL (→ nostro backend Railway)
- [ ] Sottomettere message templates per approvazione Meta:
  - Template reminder: "Ciao {{1}}! Ti ricordo la tua lezione di Pilates domani {{2}} alle {{3}} con Silvia. Per spostare, rispondimi qui!"
  - Template conferma: "Perfetto {{1}}! Sei prenotata per {{2}} alle {{3}}. Ti mando un promemoria domani. A presto!"
  - Template cancellazione: "Ho cancellato la tua lezione di {{1}} alle {{2}}. Vuoi prenotare un altro giorno?"

**Giorno 19-20: Collegare tutto**
- [ ] `whatsapp.py`: implementazione reale con 360dialog API
  - `send_message(phone, text)` → API call a 360dialog
  - `send_template(phone, template_name, params)` → per reminder/conferme
- [ ] `webhooks.py`: parsing completo payload 360dialog
  - Estrarre: numero mittente, testo messaggio, timestamp, message_id
  - Identificare cliente dal numero di telefono (lookup in DB)
  - Se cliente nuovo → creare record client automaticamente
- [ ] Flow completo end-to-end:
  1. Cliente manda messaggio su WhatsApp
  2. 360dialog gira al nostro webhook
  3. Backend classifica intent + estrae entità
  4. (Per ora) risponde con echo dell'intent: "Ho capito che vuoi prenotare giovedì alle 16"

**Giorno 21: Test end-to-end**
- [ ] Inviare messaggio reale dal proprio telefono al numero Dora
- [ ] Verificare che il sistema risponde correttamente
- [ ] Testare 10 scenari diversi, loggare errori
- [ ] Fix bug critici

**Deliverable settimana 3:** Messaggio WhatsApp reale → sistema capisce e risponde (senza ancora creare booking).

---

### SETTIMANA 4: Business Logic — Prenotazioni (Giorni 22-28)

#### Obiettivo: Dora crea, modifica e cancella prenotazioni reali.

**Giorno 22-23: Availability Engine**
- [ ] `logic/availability.py`:
  - `get_working_slots(practitioner_id, date)` → lista slot disponibili
  - `is_available(practitioner_id, datetime, duration)` → True/False
  - `find_next_available(practitioner_id, preferred_day, preferred_time)` → suggerimenti
  - Rispettare: orari di lavoro, pause tra sessioni, booking esistenti
- [ ] Test con vari scenari:
  - Slot libero → disponibile
  - Slot occupato → non disponibile
  - Fine giornata (non abbastanza tempo) → non disponibile
  - Pausa pranzo → non disponibile

**Giorno 24-25: Booking Manager**
- [ ] `logic/booking.py`:
  - `create_booking(practitioner_id, client_id, datetime, service)` → booking
    - Verifica disponibilità (double-check)
    - Crea record in DB
    - Se cliente ha pacchetto attivo → decrementa sessioni
    - Invia conferma WhatsApp al cliente
  - `cancel_booking(booking_id)` → cancella
    - Aggiorna status → "cancelled"
    - Se aveva usato sessione pacchetto → re-incrementa
    - Invia conferma cancellazione
  - `reschedule_booking(booking_id, new_datetime)` → sposta
    - Verifica disponibilità nuovo slot
    - Aggiorna record
    - Invia conferma con nuovo orario
- [ ] Gestire conflitti e edge cases:
  - Cliente prova a prenotare slot già preso → suggerisci alternative
  - Cliente prova a cancellare booking inesistente → messaggio chiaro
  - Cliente ha 2 booking lo stesso giorno → conferma quale vuole spostare

**Giorno 26-27: Conversation Flows completi**
- [ ] Implementare il flusso multi-turno:

```
FLUSSO PRENOTAZIONE:
Cliente: "Vorrei prenotare per giovedì"
Dora: "Certo! A che ora preferisci? Ho disponibile: 9:00, 10:00, 14:00, 15:00, 16:00"
Cliente: "Le 10 va bene"
Dora: "Perfetto! Ti ho prenotata per giovedì 22 maggio alle 10:00 - Pilates Individuale. Ti mando un promemoria domani. A presto!"

FLUSSO SPOSTAMENTO:
Cliente: "Posso spostare la lezione di domani?"
Dora: "Certo! Hai la lezione domani (mercoledì) alle 14:00. Quando preferiresti?"
Cliente: "Venerdì alla stessa ora"
Dora: "Venerdì alle 14:00 è libero. Sposto? ✓"
Cliente: "Sì"
Dora: "Fatto! Lezione spostata a venerdì 24 maggio alle 14:00. A venerdì!"

FLUSSO CANCELLAZIONE:
Cliente: "Domani non riesco a venire"
Dora: "Ho cancellato la tua lezione di domani alle 14:00. Vuoi prenotare un altro giorno?"

FLUSSO QUERY:
Cliente: "Quando è il mio prossimo appuntamento?"
Dora: "La tua prossima lezione è giovedì 22 maggio alle 10:00 - Pilates Individuale."

FLUSSO PACCHETTO:
Cliente: "Quante lezioni mi restano?"
Dora: "Hai 4 lezioni rimanenti nel tuo pacchetto da 10 (scade il 30 giugno). Vuoi prenotare la prossima?"
```

- [ ] Gestire il contesto "la solita ora" / "come la scorsa settimana" → lookup ultima prenotazione

**Giorno 28: Integration test completo**
- [ ] Testare ogni flusso via WhatsApp reale
- [ ] Verificare che il DB si aggiorna correttamente
- [ ] Verificare che non si creano booking duplicati
- [ ] Stress test: cosa succede se arrivano 5 messaggi in 10 secondi?

**Deliverable settimana 4:** Un cliente può prenotare, spostare, e cancellare una lezione via WhatsApp. La prenotazione esiste nel database.

---

### SETTIMANA 5: Reminder + Dashboard (Giorni 29-35)

#### Obiettivo: Reminder automatici funzionanti. Silvia ha una dashboard web.

**Giorno 29-30: Reminder automatici**
- [ ] `logic/reminders.py`:
  - Job che gira ogni ora (Railway cron o APScheduler)
  - Query: `SELECT * FROM bookings WHERE starts_at BETWEEN NOW() + 23h AND NOW() + 25h AND reminder_sent = FALSE AND status = 'confirmed'`
  - Per ogni booking trovato: invia template reminder via WhatsApp
  - Aggiorna `reminder_sent = TRUE`
- [ ] Gestire: se il template non è ancora approvato da Meta, usare messaggio free-form (dentro finestra 24h)
- [ ] Logging: tracciare ogni reminder inviato per debug

**Giorno 31-33: Dashboard web**
- [ ] Setup Next.js project in `dashboard/`
- [ ] Autenticazione semplice: magic link via email o PIN hardcoded per MVP
- [ ] API backend per dashboard:
  - `GET /api/bookings?week=2026-W21` → booking della settimana
  - `GET /api/clients` → lista clienti
  - `GET /api/packages` → pacchetti attivi
  - `POST /api/bookings` → crea booking manuale
  - `PATCH /api/bookings/:id` → modifica/cancella
- [ ] Pagine:
  - **Agenda settimanale**: griglia oraria con booking, colori per stato
  - **Clienti**: lista, ultimo appuntamento, pacchetto attivo
  - **Oggi**: vista semplificata solo per la giornata
- [ ] Mobile-responsive (Silvia lo guarderà dal telefono)

**Giorno 34-35: Override manuali**
- [ ] Da dashboard, Silvia può:
  - Bloccare uno slot (es. "non lavoro mercoledì pomeriggio")
  - Aggiungere un booking a mano (cliente che chiama a voce)
  - Cancellare un booking
  - Modificare i suoi orari di lavoro
- [ ] Le modifiche si riflettono immediatamente sulla disponibilità vista da Dora

**Deliverable settimana 5:** Reminder funzionanti + Silvia può vedere e gestire la sua agenda da browser.

---

### SETTIMANA 6: Onboarding Silvia + Go-Live (Giorni 36-42)

#### Obiettivo: Silvia usa Dora con i suoi clienti reali.

**Giorno 36-37: Preparazione dati Silvia**
- [ ] Call con Silvia (15 min):
  - Servizi: nomi esatti, durate, prezzi
  - Orari settimanali: per ogni giorno, fascia oraria
  - Pause: pranzo, tra sessioni
  - Pacchetti: offre pacchetti? Da quante lezioni? Scadenza?
  - Clienti: lista nomi + numeri di telefono (i più frequenti)
  - Domande aperte: come gestisce le cancellazioni last minute? Ha una policy?
- [ ] Inserire dati nel DB:
  - Creare record practitioner per Silvia
  - Inserire clienti abituali
  - Configurare servizi e orari

**Giorno 38-39: Test pre-lancio**
- [ ] Simulare 15-20 conversazioni realistiche
- [ ] Testare:
  - Prenotazione standard
  - Prenotazione giorno pieno → suggerimenti
  - Spostamento
  - Cancellazione
  - Domanda pacchetto
  - Messaggio ambiguo → come risponde?
  - Messaggio off-topic → risponde gentilmente
  - Due clienti prenotano stesso slot → gestione conflitto
- [ ] Fix bug trovati
- [ ] Far testare a Silvia: lei scrive come farebbe un cliente, verifichiamo

**Giorno 40: Go-live soft**
- [ ] Silvia invia messaggio ai primi 5-10 clienti:
  > "Ciao! Da oggi puoi prenotare le tue lezioni di Pilates scrivendo a questo numero: [numero Dora]. È Dora, la mia assistente — rispondile quando vuoi, anche la sera, e lei ti trova un posto. Provaci!"
- [ ] Noi monitoriamo ogni conversazione in tempo reale
- [ ] Intervento manuale immediato se qualcosa va storto

**Giorno 41-42: Monitoring e iterazione**
- [ ] Dashboard monitoring:
  - Messaggi ricevuti / giorno
  - Intent classificati correttamente vs errori
  - Booking creati con successo
  - Fallback a "non ho capito" (da minimizzare)
- [ ] Raccogliere feedback da Silvia:
  - Cosa funziona?
  - Cosa manca?
  - Cosa confonde i clienti?
- [ ] Iterare su prompt e flussi basandosi su conversazioni reali

**Deliverable settimana 6:** Silvia usa Dora nella vita reale. I clienti prenotano via WhatsApp.

---

## Post-MVP: Cosa viene dopo (Settimane 7-12)

| Settimana | Feature | Descrizione |
|-----------|---------|-------------|
| 7-8 | Package tracking avanzato | Notifiche automatiche quando il pacchetto sta finendo; promemoria rinnovo |
| 8-9 | Gestione no-show | Tracciare no-show, notificare Silvia, policy automatica |
| 9-10 | Waiting list | Se uno slot è pieno, il cliente può mettersi in lista d'attesa |
| 10-11 | Secondo professionista | Onboarding di un altro tester per validare multi-tenant |
| 11-12 | Self-service onboarding | Flusso web dove un professionista si registra da solo |

---

## Rischi e mitigazioni

| Rischio | Impatto | Probabilità | Mitigazione |
|---------|---------|-------------|-------------|
| **Meta rifiuta i template** | Non possiamo mandare reminder | Media | Sottomettere template standard, conformi alle linee guida. Avere fallback free-form. |
| **AI sbaglia prenotazione** | Silvia perde fiducia | Alta (all'inizio) | Step di conferma esplicito prima di creare booking. Fallback "Non sono sicura, ti passo a Silvia". |
| **Cliente parla in modo ambiguo** | Booking sbagliato | Alta | Multi-turno: se non sicura, Dora chiede conferma ("Intendi questo giovedì o il prossimo?") |
| **360dialog downtime** | Sistema non risponde | Bassa | Monitoring + alert. In MVP accettiamo il rischio. |
| **Numero WhatsApp bannato** | Servizio interrotto | Bassa | Rispettare linee guida Meta. Non spammare. |
| **Silvia non adotta la dashboard** | Non vede valore | Media | Dashboard semplicissima, mobile-first. Alternativa: report giornaliero WhatsApp. |
| **Clienti non scrivono a Dora** | Nessuna adozione | Media | Silvia introduce gradualmente. Prima i clienti tech-savvy. |

---

## Costi mensili stimati (fase MVP, 1 utente)

| Voce | Stima |
|------|-------|
| SIM (Iliad) | €5 |
| 360dialog / WhatsApp API (~150 conversazioni) | €5 |
| Anthropic API (Haiku, ~3000 messaggi) | €3-5 |
| Railway (backend) | €5 |
| Supabase (PostgreSQL) | €0 |
| Vercel (dashboard) | €0 |
| **Totale** | **€18-20/mese** |

---

## Cose da fare ORA (oggi)

1. [ ] **Giovanni**: Creare repo `dora-mvp` su github.com/new (privato, senza README)
2. [ ] **Giovanni**: Generare Personal Access Token su GitHub (scope: `repo`)
3. [ ] **Giovanni**: Comprare SIM Iliad/ho. nei prossimi 5 giorni
4. [ ] **Claude**: Creare struttura progetto in locale + primo push

---

## Informazioni da raccogliere da Silvia (prima del go-live)

- [ ] Quali servizi offre? (nomi, durate, se fa individuale/duo/gruppo)
- [ ] Quali sono i suoi orari di lavoro? (per ogni giorno della settimana)
- [ ] Ha pause fisse? (pranzo, altro)
- [ ] Quanti minuti tra una sessione e l'altra?
- [ ] Offre pacchetti prepagati? Se sì: quante lezioni, scadenza, prezzo
- [ ] Lista clienti abituali (nome + numero telefono) — anche solo i top 10-15
- [ ] Ha una policy di cancellazione? (es. "cancella almeno 24h prima")
- [ ] Dove lavora? (uno studio? più sedi?)
- [ ] Quante lezioni fa al giorno in media?
- [ ] Lavora nel weekend?
