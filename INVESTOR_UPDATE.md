# Dora — Build Update

**Date:** May 2026
**Stage:** Working MVP, deployed online, ready for first paying user

## Try it yourself

The MVP is live. Anyone reading this can interact with it right now:

- **Chat as a client**: <https://web-production-816f6.up.railway.app/console>
  - Try saying "ciao", then "vorrei prenotare giovedì alle 10", then "sì" to confirm.
  - Click **Demo** in the top-right to seed 5 sample clients with bookings, then explore.

- **Practitioner panel** (the view Silvia uses): <https://web-production-816f6.up.railway.app/practitioner>
  - PIN: `1234`
  - Browse the agenda, the client list (click a name for full chat history), the packages tab,
    and try the "Comandi" tab — type something like "cancella tutto lunedì" and Dora previews
    exactly what would happen before doing anything.

Both views work on mobile.

---

## What Dora is

Dora is an AI assistant that lives inside WhatsApp — the messaging app every Italian already uses. Wellness professionals (the first being Silvia, a Pilates instructor) point Dora at a phone number, and from then on, their clients book, move, and cancel lessons by chatting normally in Italian. No app to download, no website to learn, no forms to fill in.

For the professional, Dora replaces the messy mix of WhatsApp threads, paper agendas, and "I'll get back to you tonight" that absorbs hours of unbillable work every week.

---

## What we've built so far

### A working AI assistant in Italian

Dora understands free-form Italian messages — "vorrei venire giovedì alle 10", "domani non riesco", "spostami a venerdì alle 14" — and turns them into real bookings. She handles:

- **Booking** new lessons, with confirmation before anything is locked in ("Ti prenoto per giovedì alle 10 — confermi?")
- **Moving** existing lessons
- **Cancelling** lessons
- **Answering questions** like "quando è il mio prossimo appuntamento?" or "quante lezioni mi restano nel pacchetto?"
- **Onboarding new clients** by asking their name once, then letting them get to their actual request

She speaks warmly, briefly, and consistently — no robotic language, no over-explaining.

### A panel for the practitioner

Silvia logs in with a PIN and sees:

- **Her week's agenda** with one-click cancel buttons
- **Her client list** — clicking a name opens the full conversation history with Dora
- **Active packages** — which clients have prepaid lessons left, with low-balance flags
- **A natural-language command box** — she can type "cancella tutto domani, sto male" and Dora previews exactly what will be cancelled before any action is taken

### Calendar sync

Dora's bookings sync automatically to a Google Calendar that Silvia already uses. She doesn't have to learn another tool — her existing calendar app shows everything.

### Reminders

Each booking gets a WhatsApp reminder 24 hours before, so no-shows drop and clients don't forget.

### A live testing platform

We've built a public web console where anyone can chat with Dora as if they were a Pilates client and watch the database update in real time. This is how we'll show Silvia, friends, and prospective customers what Dora can do — without committing to a real WhatsApp number first.

---

## What this took technically (in plain language)

- **AI cost-and-speed efficiency**: most simple messages ("ciao", "domani alle 10", "quante lezioni ho?") are answered without calling the AI at all, using a deterministic rule layer. The AI is only invoked when the message is genuinely ambiguous. This makes Dora faster and dramatically cheaper to run at scale.
- **Safety nets everywhere**: bookings only confirm after the user says "sì". Bulk operations from Silvia's side ("cancella tutto domani") show a preview with the exact list of affected lessons before doing anything. Every conversation is logged for review.
- **Built to scale to many practitioners**: the data model and code are scoped per professional from day one. Onboarding a second customer is a configuration change, not a rewrite.
- **No vendor lock-in**: hosted on Railway, database on Supabase, calendars on Google — all interchangeable services with active competitors.

---

## Where we are right now

**Everything works end-to-end** through the test console. We're one component away from go-live: a dedicated SIM card and a 360dialog (WhatsApp Business) account, which is administrative paperwork rather than engineering work. As soon as that's in place, Silvia's clients can start texting Dora directly.

**Cost to run a single practitioner:** roughly €18-20/month (SIM, WhatsApp API, AI calls, hosting, database). Margin is healthy at any reasonable subscription price (€30-60/month).

---

## What's next

Once Silvia is live:

1. **Validate with real conversations.** Watch where Dora handles things gracefully and where she stumbles, refine accordingly.
2. **Expand to a second practitioner** to confirm the multi-tenant story works.
3. **Self-service onboarding** — a flow where any wellness professional can sign up, configure their hours, and have Dora running in 15 minutes.
4. **Premium features** for retention: package renewals, no-show policies, waitlists, payment links.

The hardest part — building an AI booking assistant that feels natural in Italian and doesn't make embarrassing mistakes — is done. Everything from here is distribution and polish.
