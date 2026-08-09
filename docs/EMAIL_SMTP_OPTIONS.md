# Email / SMTP options (no Microsoft credentials)

The app sends email for reports, password resets, and MMR. Configure `.env` (or Render env vars).

**Render free web services block outbound SMTP** (ports 25, 465, 587). Gmail SMTP will **time out** there. Use **HTTPS** instead:

- **Brevo (recommended):** **`BREVO_API_KEY`** + **`MAIL_DEFAULT_SENDER`**
- **Mailjet:** **`MAILJET_API_KEY`** + **`MAILJET_SECRET_KEY`** + **`MAIL_DEFAULT_SENDER`**, *or* the same **API key + secret** as **`MAIL_USERNAME`** / **`MAIL_PASSWORD`** with **`MAIL_SERVER=in-v3.mailjet.com`** (the app switches to Mailjet's REST API automatically on Render).

Send order: Brevo REST → Mailjet REST → SMTP.

On a **paid** Render instance, normal SMTP usually works again for providers that use SMTP.

---

## Recommended: **Brevo**

- Free tier available for transactional email; see [brevo.com](https://www.brevo.com).
- **Sign up** → **Settings** → **SMTP & API** → create an **API key**.
- **Verify** your sender (or domain) in Brevo before sending.

### REST / HTTPS (Render **free** — recommended)

```env
BREVO_API_KEY=xkeysib-...
MAIL_DEFAULT_SENDER=noreply@injaaz.ae
```

The app calls **`https://api.brevo.com/v3/smtp/email`** so outbound SMTP is not required.

### SMTP (local or Render paid)

```env
MAIL_SERVER=smtp-relay.brevo.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-brevo-login-email
MAIL_PASSWORD=your-brevo-smtp-key
MAIL_DEFAULT_SENDER=noreply@injaaz.ae
```

---

## Alternative: **Mailjet**

- **Free tier** available for outbound send; see [mailjet.com](https://www.mailjet.com) for limits.
- **Sign up** → **Account** → **SMTP and SEND API** → copy **API Key** and **Secret Key**.
- **Verify** your sender or domain in Mailjet before sending.

### REST / HTTPS (Render **free** — recommended)

```env
MAILJET_API_KEY=your-mailjet-api-key
MAILJET_SECRET_KEY=your-mailjet-secret-key
MAIL_DEFAULT_SENDER=noreply@injaaz.ae
```

The app calls **`https://api.mailjet.com/v3.1/send`** so outbound SMTP is not required.

Optional: set **`MAILJET_USE_REST=true`** anywhere to force Mailjet HTTPS even off Render (e.g. testing).

### SMTP (best on Render **paid** or local dev)

```env
MAIL_SERVER=in-v3.mailjet.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-mailjet-api-key
MAIL_PASSWORD=your-mailjet-secret-key
MAIL_DEFAULT_SENDER=noreply@injaaz.ae
```

---

## SendGrid (free trial, then paid)

- **Free:** 100 emails/day for 60 days.
- **Sign up:** [sendgrid.com](https://sendgrid.com) → **Settings** → **API Keys** → **Create API Key** (scope: **Mail Send**).
- **Username is the literal word** `apikey`; **password** is the API key you created.

```env
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=apikey
MAIL_PASSWORD=your-sendgrid-api-key
MAIL_DEFAULT_SENDER=noreply@injaaz.ae
```

Verify your sender/domain in SendGrid.

---

## Personal Gmail (@gmail.com)

You can use your **personal Gmail** (e.g. you@gmail.com). Emails are sent **from** that address. Recipients stay restricted to @injaaz.ae in the app.

**Steps:**

1. **Turn on 2-Step Verification:** [myaccount.google.com/security](https://myaccount.google.com/security) → **2-Step Verification** → turn it on.
2. **Create an App Password:** [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) → App: **Mail**, Device: **Other** (e.g. "Injaaz") → **Generate**. Copy the 16-character password (no spaces in `.env`).
3. In **`.env`** set:

```env
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=yourname@gmail.com
MAIL_PASSWORD=your-16-char-app-password
MAIL_DEFAULT_SENDER=yourname@gmail.com
```

Restart the app and try **Send Email**.

---

## Google Workspace (if @injaaz.ae is on Google)

If your organisation uses Google for **@injaaz.ae**:

1. Use the mailbox you want to send from (e.g. `noreply@injaaz.ae`).
2. In that Google account: **Security** → **2-Step Verification** (must be on) → **App passwords** → create one for "Mail".
3. Use that **app password** (not your normal login password).

```env
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=noreply@injaaz.ae
MAIL_PASSWORD=your-16-char-app-password
MAIL_DEFAULT_SENDER=noreply@injaaz.ae
```

---

## Summary

| Provider        | Free tier        | Best for                          |
|-----------------|------------------|------------------------------------|
| **Mailjet**     | Free tier (send) | HTTPS REST on Render; Parse API for ticket intake (paid) |
| **Personal Gmail** | With 2-Step + App pwd | Quick setup with your @gmail.com |
| SendGrid        | 100/day, 60 days | Short-term trial                   |
| Google Workspace| With your domain | If injaaz.ae uses Google           |

After editing `.env`, restart the Flask app. On Render, set the same variables in the dashboard and redeploy.
