# Email-to-Draft-Ticket intake setup

Anyone can raise a Service Ticket by sending an email to a dedicated Injaaz address —
no login required. The system parses the email and creates a `status='draft'` ticket
that a supervisor/admin reviews and converts into a real ticket under
**Tickets → Draft Tickets (Email)**. See the in-app guide at
**Tickets → Settings → Email a Ticket** for the format shared with requesters.

This uses **Mailjet Parse API** for inbound mail, paired with the same Mailjet account
used for outbound notifications (see `docs/EMAIL_SMTP_OPTIONS.md`).

**Note:** Mailjet Parse API requires a **Crystal plan or higher** (paid). Outbound send
can use Mailjet's free tier; inbound parsing does not.

---

## How it works

```
requester email → intake MX (parse.mailjet.com) → Mailjet Parse API → POST to our webhook
  → /tickets/api/inbound-email/<TICKET_INBOUND_WEBHOOK_SECRET>
  → draft Ticket created, supervisors notified
```

Code: `module_ticketing/routes.py` — `inbound_email_webhook()`, `_normalize_mailjet_parse_payload()`,
`_process_inbound_email_intake()`.

Every inbound call (successful, duplicate, or failed) is logged to the `ticket_email_intakes`
table (`TicketEmailIntake` model) for auditing/debugging.

---

## One-time setup

### 1. Pick a receiving subdomain

Use a subdomain dedicated to intake, e.g. `intake.injaaz.ae` (separate from your
sending domain). Any mailbox at that subdomain works — e.g. `tickets@intake.injaaz.ae`.

### 2. Point MX records at Mailjet

In your DNS provider, add for `intake.injaaz.ae` (or whichever subdomain you chose):

| Type | Priority | Value |
|------|----------|-------|
| MX   | 10       | `parse.mailjet.com.` |

DNS propagation can take a few hours — do this early.

### 3. Generate a webhook secret

Pick a long random string, e.g.:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Add it to Render env vars (and `.env` locally) as:

```env
TICKET_INBOUND_WEBHOOK_SECRET=<the generated value>
```

The webhook URL is then:

```
https://<your-app-host>/tickets/api/inbound-email/<TICKET_INBOUND_WEBHOOK_SECRET>
```

Requests to that path with the wrong (or missing) secret get a `404` — there is no
JWT/CSRF check on this route since Mailjet cannot send auth headers we control.

### 4. Register the parse route with Mailjet

Using your Mailjet API credentials (`MAILJET_API_KEY` / `MAILJET_SECRET_KEY`):

```bash
curl -X POST https://api.mailjet.com/v3/REST/parseroute \
  -u "$MAILJET_API_KEY:$MAILJET_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "Url": "https://<your-app-host>/tickets/api/inbound-email/<TICKET_INBOUND_WEBHOOK_SECRET>",
    "Email": "tickets@intake.injaaz.ae"
  }'
```

Replace `Email` with the intake address you chose. Mailjet will POST parsed JSON to `Url`
when mail arrives at that address.

### 5. (Optional) Set the display address shown in-app

The "Email a Ticket" settings tab shows a suggested intake address to requesters. By
default it displays `tickets@intake.injaaz.com` — override with:

```env
TICKET_INTAKE_EMAIL=tickets@intake.injaaz.ae
```

### 6. Test end-to-end

1. Send an email to `tickets@intake.injaaz.ae` (or your chosen address) following the
   format shown in **Tickets → Settings → Email a Ticket**.
2. Within a few seconds, check **Tickets → Draft Tickets (Email)** as a supervisor/admin.
3. If nothing appears, check the `ticket_email_intakes` table (or app logs).

**Local simulation** (no Mailjet needed):

```bash
curl -s -X POST "http://localhost:5002/tickets/api/inbound-email/<your-secret>" \
  -H "Content-Type: application/json" \
  -d '{
    "Sender": "requester@example.com",
    "From": "Requester Name <requester@example.com>",
    "Recipient": "tickets@intake.injaaz.ae",
    "Subject": "[Project Alpha] Plumbing / high — Leaking pipe",
    "Text-part": "Property: Building A\nZone: Floor 2\nUnit: 201\n\nWater leaking under sink.",
    "Headers": {"Message-ID": "<test-001@example.com>"}
  }'
```

---

## Notes

- **Attachments:** Mailjet includes image attachments as base64 in the webhook payload
  (`Attachment1`, `Attachment2`, …). Only image types (png/jpg/jpeg/gif/webp/heic/heif)
  are stored as `TicketImage` rows; other file types are noted on the ticket but not stored.
- **Unknown senders:** if the sender's email doesn't match a registered `User`, the
  draft is attributed to the system **"Email Intake"** account — the real sender's
  name/email is still shown on the draft.
- **De-duplication:** Mailjet retries webhook calls that don't return `200` promptly; we
  de-duplicate on the email's `Message-Id` header, so retries won't create duplicate
  drafts.
