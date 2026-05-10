# Dora — Engineering Handoff

> **Audience:** a new engineer taking over the codebase with no prior context.
> **Goal:** by the end of this document you should be able to run Dora locally,
> understand every component, and know exactly what's left to build.

**Last updated:** 2026-05-10
**Repo:** https://github.com/giovannifoglietta/dora-mvp
**Production URL:** https://web-production-816f6.up.railway.app/

---

## 1. The product in one paragraph

Dora is an AI assistant that lives inside WhatsApp. Wellness professionals
(first user: Silvia, a Pilates instructor in Italy) point Dora at a phone
number, and from then on their clients book, move, and cancel lessons by
chatting in normal Italian. No app to download, no website to learn. For the
practitioner, Dora replaces the messy mix of WhatsApp threads and paper
agendas. The product is built around the framing: *"Dora is a booking workflow
engine with a conversational WhatsApp interface"* — the AI translates messy
text into structured intents; deterministic code owns everything else.

### Pricing target
Operating cost per practitioner: ~€18-20/mo (SIM + 360dialog + Anthropic +
Railway + Supabase). Target subscription: €30-60/mo. Healthy margin.

---

## 2. The original plan & where we are

The MVP plan lives in [`PIANO_MVP.md`](./PIANO_MVP.md) (Italian). It is
**6 weeks** broken into:

| Week | Goal | Status |
|---|---|---|
| 1 | Repo + FastAPI skeleton + Railway deploy | ✅ Done |
| 2 | AI pipeline (intent + entity extraction in Italian) | ✅ Done |
| 3 | DB schema + 360dialog WhatsApp integration | ✅ DB done; WhatsApp blocked on SIM |
| 4 | Booking business logic (create/cancel/reschedule) | ✅ Done |
| 5 | Reminders + practitioner dashboard | ✅ Done |
| 6 | Onboarding Silvia + go-live | 🟡 Blocked on SIM card |

We then went well beyond the original plan. Since it's all working code, the
list of what's actually built is below in §4.

---

## 3. Quick start — running locally

```bash
git clone https://github.com/giovannifoglietta/dora-mvp.git
cd dora-mvp
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in API keys, see §5
python -m backend.seed  # one-time: create the practitioner record
uvicorn backend.main:app --reload
```

Browse to:
- `http://localhost:8000/` — health
- `http://localhost:8000/console` — public test console (chat + DB state)
- `http://localhost:8000/practitioner` — practitioner panel (PIN: `1234`)

Run tests:
```bash
pytest backend/tests/
# 37 unit tests, all passing
```

Apply a new database migration:
```bash
python -c "
import psycopg, os
from dotenv import load_dotenv
load_dotenv()
conn = psycopg.connect(os.environ['DATABASE_URL'])
with open('backend/db/migrations/00X_xxx.sql') as f:
    sql = f.read()
with conn.cursor() as cur:
    cur.execute(sql)
conn.commit()
conn.close()
"
```

---

## 4. What's been built (component tour)

### 4.1 High-level architecture

```
WhatsApp client (Silvia's clients)
    → 360dialog (BSP, currently STUBBED — needs SIM)
        → POST /webhook (FastAPI, backend/webhooks.py)
            → orchestrator.handle_message(phone, text)
                ├─ practitioner-phone? → practitioner_nlp.execute_instruction
                └─ client message:
                    ├─ rules.try_parse (deterministic fast path)
                    ├─ analyze_message (Haiku, 1 call) if rules miss
                    ├─ name capture if new client
                    ├─ confirmation flow (no booking without "sì")
                    └─ booking/cancel/reschedule via logic/booking.py
                        └─ syncs to Google Calendar (best-effort)
            ← reply text
        ← 360dialog sends reply to client

Practitioner (Silvia in browser)
    → /practitioner — login (PIN), Today / Agenda / Clienti / Pacchetti / Blocchi / Impostazioni / Comandi tabs
        → /practitioner/api/* (FastAPI routes in backend/practitioner.py)
        → Same database as WhatsApp side
```

### 4.2 Tech stack

| Layer | Choice | Why |
|---|---|---|
| Runtime | Python 3.13 (3.9 locally) | Anthropic SDK + ML libs are Python-native |
| Web framework | FastAPI | Async, lightweight, automatic OpenAPI |
| ORM | SQLAlchemy 2.0 (sync) | Mature, well-documented; async DB is overkill for our scale |
| Database | PostgreSQL via Supabase | Managed, EU region, 5GB free tier |
| AI | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) | Italian-strong, cheap, fast |
| Hosting | Railway | Cheap, GitHub-deploy, EU region |
| Frontend | Hand-rolled HTML/CSS/JS in `backend/static/` | No build step, mobile-responsive, fast iteration |
| Calendar | Google Calendar API (OAuth + service-account fallback) | Practitioners already use Google |
| WhatsApp | 360dialog (BSP) — **stubbed today** | Italian-friendly BSP, needs SIM provisioning |

### 4.3 Repository layout

```
backend/
├── main.py              # FastAPI app entry; mounts routers
├── config.py            # Settings from .env (Pydantic BaseModel)
├── timezone.py          # ROME_TZ singleton (Europe/Rome)
├── webhooks.py          # WhatsApp webhook + /test/message endpoint
├── whatsapp.py          # 360dialog client (stubs when API key missing)
├── orchestrator.py      # The brain: routes intents to actions, manages state
├── responses.py         # All Italian copy in one module (tone-tuneable)
├── admin.py             # /api/state, /api/reset, /api/seed-demo, /api/gcal-status
├── practitioner.py      # /practitioner/* routes (login, agenda, blocks, oauth, NL commands)
├── seed.py              # `python -m backend.seed` to create Silvia
│
├── ai/
│   ├── analyzer.py      # SINGLE-call Haiku analyzer (intent + entities)
│   ├── classifier.py    # legacy: separate intent classifier (still used by tests of older flows)
│   ├── extractor.py     # legacy: separate entity extractor
│   ├── name_extractor.py    # extract first/last name from intro messages
│   ├── practitioner_nlp.py  # parse Silvia's NL commands ("cancella tutto domani")
│   ├── rules.py         # DETERMINISTIC parser, runs before LLM
│   ├── prompts.py       # Haiku system prompts
│   └── context.py       # In-memory conversation state (TTL 30min)
│
├── logic/
│   ├── availability.py  # Slot generation, conflict detection (bookings + time blocks)
│   ├── booking.py       # create/cancel/reschedule + package decrement + GCal sync
│   ├── packages.py      # active_package, sessions_remaining, create_package
│   └── reminders.py     # 24h-before WhatsApp reminders
│
├── integrations/
│   ├── google_calendar.py   # Sync logic, OAuth-first / service-account-fallback
│   └── google_oauth.py      # OAuth 2.0 flow (authorize URL, code exchange)
│
├── models/
│   └── schema.py        # SQLAlchemy ORM models
│
├── db/
│   ├── database.py      # Engine + SessionLocal
│   └── migrations/      # 001-005 SQL files (run manually, no Alembic)
│
├── static/
│   ├── index.html       # /console — public test chat UI
│   └── practitioner.html # /practitioner — Silvia's panel
│
└── tests/
    ├── test_rules.py    # 26 tests for the deterministic parser
    └── test_responses.py # 11 tests for response templates
```

### 4.4 Data model

Five core tables + auxiliaries. All defined in `backend/models/schema.py` and
created by migrations 001-005.

| Table | Purpose | Key fields |
|---|---|---|
| `practitioners` | One row per professional. Today: just Silvia. | `name`, `phone`, `working_hours` (JSONB), `services` (JSONB), `gcal_oauth_*` |
| `clients` | End users (Pilates students). | `phone` (unique), `first_name`, `last_name`, `practitioner_id` |
| `bookings` | Lessons. | `starts_at` (TZ-aware), `status`, `gcal_event_id`, `practitioner_id`, `client_id` |
| `packages` | Prepaid lesson bundles. | `total_sessions`, `used_sessions`, `expiry_date` |
| `messages` | Audit log of every inbound/outbound message. | `direction`, `body`, `intent`, `entities` (JSONB), `confidence` |
| `time_blocks` | Practitioner-defined unavailable periods (vacation, sick day). | `starts_at`, `ends_at`, `reason` |

**Important schema notes:**
- All datetimes are `TIMESTAMPTZ` and stored in UTC. The app code converts to
  `Europe/Rome` for display via `backend/timezone.ROME_TZ`.
- `clients.phone` is `UNIQUE` — a phone number identifies a client globally
  (single-tenant assumption). This will need a composite index on
  `(practitioner_id, phone)` once we go multi-tenant.
- Migrations are **manual**: open `backend/db/migrations/00X_*.sql` and run it
  against the DB. There is no Alembic.

### 4.5 Conversation flow (the brain)

`backend/orchestrator.py::handle_message(db, phone, text, profile_name=None)`
is the entry point for every inbound message. It does roughly:

1. **Find the practitioner** (only one today: Silvia). If the inbound phone
   matches the practitioner's number, route to `practitioner_nlp` instead and
   return early — Silvia can text her own commands like "cancella tutto domani".
2. **Find or create the client.** Update `last_seen`.
3. **Check `_replaying` flag** to avoid double-logging during recursive
   onboarding flows.
4. **Onboarding gate**: if `client.first_name` is null → ask for name. The
   user's original message is saved as `original_text` in conversation
   context, then *replayed* once we've got the name (so "ciao sono Marco
   vorrei prenotare giovedì alle 10" works in one beat).
5. **Confirmation gate**: if `pending_intent == "confirm_book"` and the message
   parses as a confirmation/negation → resolve.
6. **Keyword shortcuts** (no LLM): "aiuto", "help", etc.
7. **Try the rule-based parser** (`rules.try_parse`). Catches greetings,
   common booking phrases, package queries, and date/time-only continuations.
   Logs `_parsed_by: "rules"` on the message row.
8. **Fall back to `analyze_message`** (Haiku, single call returns intent +
   confidence + entities).
9. **Dispatch** to `_handle_book`, `_handle_cancel`, `_handle_reschedule`,
   query, package_info, or fallback.
10. **`_handle_book`** never auto-creates. It proposes and stores the proposed
    booking in conversation context. The booking is only committed when the
    user confirms.

The conversation context (`backend/ai/context.py`) is **in-memory** with a
30-minute TTL. This is intentional for MVP simplicity. The advisor review
(see `FIXES.md` and conversation transcripts) flagged this — for production
you want a `conversation_sessions` Postgres table.

### 4.6 Practitioner panel

`backend/static/practitioner.html` is a single-page HTML app served by
`backend/practitioner.py`. Six tabs:

| Tab | Backed by |
|---|---|
| **Agenda** — today card + weekly grid + manual booking modal | `/api/today`, `/api/agenda?week_start=`, `/api/bookings` (POST/DELETE) |
| **Clienti** — list, click to open conversation history | `/api/clients`, `/api/messages/{client_id}` |
| **Pacchetti** — create + list active packages | `/api/packages` (GET/POST) |
| **Blocchi** — vacation, day-off, custom range | `/api/blocks` (GET/POST/DELETE) |
| **Impostazioni** — Google Calendar connection, working hours, services | `/api/gcal/*`, `/api/settings` PATCH, `/api/me` |
| **Comandi** — natural-language instructions ("cancella tutto domani") | `/api/instruct` (with confirm flow) |

Auth is a PIN cookie (default `1234`, override with `PRACTITIONER_PIN` env var)
that resolves to a single Practitioner row. Cookie is httponly + samesite=lax.

### 4.7 Test console

`backend/static/index.html` is the public chat tester at `/console`. WhatsApp-
styled UI with a live state panel. Key features for demos:
- **Demo button** seeds 5 fake clients with bookings and a low-balance package
- **Phone input** lets you simulate different clients
- **Reset button** wipes everything except the practitioner record
- **Mobile responsive** with bottom-tab switcher (Chat / Stato)

### 4.8 Key design decisions and *why*

These have come up multiple times in iteration. Don't re-litigate without
strong reason.

1. **Deterministic replies, AI only for parsing.** The LLM never writes user-
   facing copy. All replies live in `backend/responses.py`. This makes the
   tone consistent and tests trivial.
2. **Confirm before booking.** Earlier the AI auto-booked. Caused phantom
   bookings when users were just asking about availability. `_handle_book`
   now always proposes ("Ti prenoto per X — confermi?") and waits for "sì".
3. **Per-practitioner OAuth + service-account fallback.** Onboarding new
   practitioners with service-account-share is too fiddly to scale. OAuth
   is the production path (Phase C). Service account stays as a single-tenant
   testing fallback.
4. **Single LLM call per message.** `analyze_message()` returns intent +
   entities + confidence in one Haiku request. The earlier two-call design
   was 2x slower and 2x more expensive.
5. **Sync SQLAlchemy + async FastAPI.** Pragmatic for MVP scale. Don't
   migrate to async DB without measuring.
6. **In-memory conversation state.** Intentional MVP simplicity. The 30-min
   TTL covers the realistic case. Persist when you have multiple instances
   or need to survive restarts mid-conversation.
7. **Italian-first.** Prompts, replies, error messages all in Italian. Don't
   English-ify the assistant — the UX premise depends on it feeling local.
8. **Best-effort calendar sync.** Calendar errors are logged, never raised.
   Bookings always succeed in our DB even if Google is down. The dashboard
   could later show a "sync failed, retry" indicator (not built yet).

---

## 5. Environment variables

| Var | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | Claude Haiku for NLU |
| `DATABASE_URL` | yes | Use Supabase **transaction pooler** URL (port 6543, IPv4) |
| `WHATSAPP_WEBHOOK_TOKEN` | yes | Random string for Meta webhook verify handshake |
| `WHATSAPP_API_KEY` | when SIM live | 360dialog API key. Empty → console stub mode |
| `PRACTITIONER_PIN` | optional | Defaults to `1234` |
| `GOOGLE_OAUTH_CLIENT_ID` | for OAuth flow | OAuth web-application client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | for OAuth flow | OAuth client secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | for OAuth flow | e.g. `https://<host>/practitioner/api/gcal/callback` |
| `PUBLIC_BASE_URL` | optional | Used to derive redirect URI if not explicitly set |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | for SA fallback | Base64-encoded service account JSON |
| `GOOGLE_CALENDAR_ID` | for SA fallback | Single shared calendar ID |
| `APP_ENV` | optional | `production` enables `secure` cookies |

Common gotcha: pasting raw JSON into Railway sometimes mangles newlines inside
the PEM private key. We added base64 acceptance + a JSON-repair fallback in
`backend/integrations/google_calendar.py::_parse_credentials` for this case.

---

## 6. Deploy / ops

### Hosting
- **Backend**: Railway, single web service, GitHub-connected (auto-deploy on
  push to `main`). URL: `web-production-816f6.up.railway.app`.
- **Database**: Supabase (project ID `uxpkshiqcyywddodixqz`). Use the
  **transaction pooler** URL (`...pooler.supabase.com:6543`) — Railway can't
  reach Supabase's direct IPv6 endpoint.
- **Cron**: not yet wired. Reminders are exposed via `POST /api/send-reminders`;
  any external cron (Railway cron, GitHub Actions, cron-job.org) can hit it
  hourly.

### Useful commands
```bash
# Re-seed Silvia (idempotent)
python -m backend.seed

# Run tests
pytest backend/tests/

# Manual DB inspection
psql $DATABASE_URL

# Check Google Calendar integration status (deployed)
curl https://web-production-816f6.up.railway.app/api/gcal-status

# Trigger reminder send manually
curl -X POST https://web-production-816f6.up.railway.app/api/send-reminders
```

### Diagnostic endpoints (kept around intentionally)
- `GET /api/gcal-status` — confirm the service-account integration is wired
- `POST /api/gcal-test` — create a real test event right now
- `GET /api/state` — DB snapshot used by the test console
- `POST /api/reset` — wipe all clients/bookings/messages
- `POST /api/seed-demo` — seed 5 demo clients with bookings

---

## 7. Audit history & past advisor reviews

Two external reviews shaped the codebase. Both files are in the repo:

- **`FIXES.md`** — initial code audit. 8 fixes (1-7 are done, #8 superseded
  by the current rules-based fast path). Scroll to the "SUMMARY — Execution
  Order" table to see status.
- **`DORA_CODER_ADVISOR_REVIEW.md`** — product/architecture review. We
  agreed with #1 (rule-based fast path), #8 (centralize replies), #10 (tests),
  and the onboarding simplification. We deliberately *deferred* #2 (state
  machine in Postgres), #3 (split orchestrator into layers), #4 (events
  table), #5 (package ledger), #7 (single dashboard endpoint), #9 (metrics)
  as premature for current scale. The reasoning is in the conversation
  transcript and stands.

The earlier `INVESTOR_UPDATE.md` and `INVESTOR_UPDATE.html`/`.pdf` are a
non-technical recap suitable for sharing with stakeholders.

---

## 8. What's left to build

In priority order, what a new engineer should pick up.

### Tier 1 — Unblocks go-live (do these to ship to Silvia)

1. **Provision a SIM card and 360dialog account.** This is administrative,
   not engineering. Order:
   - Buy an Italian SIM (Iliad or ho. recommended). Activate it.
   - Create a Meta Business Account at business.facebook.com.
   - Create a 360dialog account at hub.360dialog.com.
   - Connect the Meta account to 360dialog and register the SIM as a
     WhatsApp Business number.
   - Submit message templates for Meta approval (reminder, booking
     confirmation, cancellation). Templates are documented in `PIANO_MVP.md`.
   - Set `WHATSAPP_API_KEY` on Railway → the existing `whatsapp.send_message`
     stub becomes live.
   - Configure 360dialog's webhook URL to
     `https://web-production-816f6.up.railway.app/webhook`.

2. **Configure the OAuth consent screen for production.** Currently in
   "Testing" mode (cap of 100 users). For >100, submit for Google verification
   — about 2-4 weeks of paperwork.

3. **Set up the reminder cron.** Pick one:
   - Railway cron (Settings → Cron Schedule, hourly: `0 * * * *` running
     `curl -X POST $RAILWAY_PUBLIC_URL/api/send-reminders`)
   - GitHub Actions workflow with `schedule:` trigger
   - cron-job.org (free, simple)

4. **Get Silvia's real configuration** (15-min call):
   - Exact working hours per day
   - Service names, durations, prices (defaults are placeholders)
   - Package offerings and pricing
   - Cancellation policy
   - Top 10-15 clients to pre-seed
   Update `backend/seed.py::SILVIA_DATA` accordingly.

### Tier 2 — Polish for first real users (1-2 days)

5. **Calendar sync status indicator.** When `create_event` returns None,
   the booking quietly desyncs. Add a banner in the practitioner agenda
   for bookings with `gcal_event_id IS NULL` showing "non sincronizzato"
   with a "riprova" button that re-attempts the sync.

6. **Reschedule from the agenda.** Today only cancel works. Add drag-to-move
   or a "sposta" button that opens the booking-time picker.

7. **Quick clients edit.** From the Clienti tab, click a client → edit name,
   add notes. Today new clients onboarded via WhatsApp can have wrong names
   and there's no UI to fix them.

8. **Reminder copy A/B.** The current reminder text is generic. After the
   first 2 weeks, look at conversion (cancellations vs no-shows) and tune.

9. **End-to-end orchestrator tests.** Today we have 37 unit tests for pure
   logic (rules, responses), but none for the conversation orchestrator
   itself. Use SQLite in-memory + fake Anthropic client. Goal: ~10 flow
   tests covering the major user journeys (book, cancel, reschedule,
   onboard, package query).

### Tier 3 — Scale to 10+ practitioners (1-2 weeks)

10. **Self-service onboarding.** A web flow at `/signup` where any
    practitioner can:
    - Create their account (email + password or magic link)
    - Configure hours, services, prices
    - Connect their Google Calendar (OAuth, already built)
    - Get their unique webhook URL / phone number setup instructions
    Today only Silvia exists; the data model already scopes by
    `practitioner_id` so this is mostly UI work.

11. **Multi-practitioner phone routing.** Today a single inbound webhook
    serves one practitioner. For multi-tenant, the webhook payload's
    `to_number` must route to the right practitioner row. Add a
    `practitioner.whatsapp_business_number` column with a unique index and
    look up by it in `webhooks.py`.

12. **Composite uniqueness on clients.** Today `clients.phone` is globally
    unique. Make it `(practitioner_id, phone)` so two different practitioners
    can have the same phone in their books.

13. **Practitioner self-edit profile picture, bio.** Cosmetic but expected.

### Tier 4 — Deferred from advisor reviews (do when there's a real reason)

14. **Conversation state in Postgres** (advisor #2). Today in-memory.
    Reason to do this: when restarts mid-confirm get noticeable to users.

15. **Events table** (advisor #4). General audit log beyond just messages.
    Reason to do this: when you can't debug an issue from `messages` +
    `bookings` alone.

16. **Package ledger** (advisor #5). Replace the mutable `used_sessions`
    counter with a transaction log. Reason to do this: when you see counter
    drift bugs in production.

17. **Dashboard summary endpoint** (advisor #7). Single API call returning
    "what needs Silvia's attention". Reason to do this: when the practitioner
    panel feels slow or the agenda+clients+packages serial fetches feel
    noticeably bad.

18. **Metrics** (advisor #9). Reason to do this: when you have ≥3 paying
    practitioners and need to compare engagement.

19. **`needs_human` intent / handoff queue.** When Dora doesn't know how to
    answer, route to a "Silvia review" queue in the dashboard. Reason to do
    this: when you see real off-topic messages in the `messages` table that
    can't be triaged automatically.

### Tier 5 — Premium features (revenue)

20. **No-show tracking + policy enforcement.**
21. **Waitlists** when a slot is full.
22. **Payment links** in confirmations.
23. **Recurring bookings** ("ogni giovedì alle 10 per 8 settimane").
24. **Package auto-renewal flows.**

---

## 9. Known issues and gotchas

- **Conversation state is in-memory.** Restart of Railway = pending
  confirmations are lost. Documented but not yet fixed (Tier 4).
- **`whatsapp.send_message` returns True on stub mode.** Don't trust the
  return value as "real WhatsApp delivered" until `WHATSAPP_API_KEY` is set.
- **Italian weekday parsing was buggy.** Haiku occasionally said "lunedì" =
  Tuesday. Fixed via `rules._resolve_relative_date` and the explicit
  calendar in the analyzer prompt. If it regresses, check `analyzer._PROMPT`
  and the `_correct_named_day` post-validation.
- **Google API JSON via env var on Railway.** Railway sometimes turns
  escaped `\n` into literal newlines, breaking the PEM key. The fallback
  in `google_calendar._parse_credentials` handles this, but the
  recommended approach is to base64-encode the JSON before pasting.
- **Daylight saving time.** All calculations use `Europe/Rome`, which
  handles DST. Watch for issues in the spring/fall switchover; add tests
  if real users hit it.
- **The `classifier.py` and `extractor.py` modules are LEGACY.** Kept for
  backward compatibility but the orchestrator now uses `analyzer.py` (single
  call). Don't add new logic to the legacy files; delete them once you're
  confident nothing imports them.

---

## 10. Where to look when something breaks

| Symptom | Where to look |
|---|---|
| Webhook returns 500 | `backend/webhooks.py::receive_message` (we wrap in try/except so this should be impossible — if it is, the bug is in handle_message itself) |
| AI gives wrong intent | `backend/ai/analyzer.py::_PROMPT`. Check the `messages` table for `intent` + `confidence` + `_parsed_by` fields |
| Booking conflicts wrong | `backend/logic/availability.py::get_working_slots` — most likely a TZ issue |
| Calendar not syncing | `GET /api/gcal-status`. Check Railway env vars. For OAuth, look at the `gcal_oauth_*` columns in the practitioner row |
| Italian copy wrong | `backend/responses.py` |
| Practitioner can't login | `backend/practitioner.py::login`. Compare PIN against `settings.practitioner_pin` |
| Reminder not firing | Hit `POST /api/send-reminders` manually. Check `bookings.reminder_sent` and `starts_at` window |
| Mobile UI broken | `backend/static/index.html` and `practitioner.html`. CSS is hand-rolled, check media queries |

---

## 11. Contact / decisions log

Product decisions and historical context live in:
- This file (`HANDOFF.md`)
- `PIANO_MVP.md` — original 6-week plan (Italian)
- `FIXES.md` — first audit, line-by-line fix list
- `DORA_CODER_ADVISOR_REVIEW.md` — second audit, architecture-level
- `INVESTOR_UPDATE.md` — non-technical recap
- Git history: every commit message explains *why*, not just *what*

When in doubt about a design decision, run `git log -p <file>` to see how
something evolved. Most non-trivial choices have a commit explaining the
reasoning.

---

**End of handoff.** Welcome to the team.
