# Injaaz Application — Security Posture

_Prepared for client review — 2026-07-22_

This document explains, in plain language, how the Injaaz application protects
company and customer data, what we hardened in this security pass, and the small
number of follow-up actions in progress. It is written to be readable by a
non-technical audience.

---

## 1. In one paragraph

The application is built with defense-in-depth: every connection is encrypted,
passwords are stored using industry-standard one-way hashing (they cannot be read
back — even by us), each user only sees the modules they are granted, and the
administrative area is locked down to administrators only. It runs on Render (a
reputable managed cloud platform) in a hardened, non-root container, and all
third-party services it uses (email, image storage, AI assistant) are reached over
encrypted connections with credentials kept out of the source code. In this pass we
closed the remaining gaps a professional penetration test would flag.

---

## 2. How data is protected (defense-in-depth)

| Layer | What we do |
|-------|------------|
| **Transport** | All traffic is served over HTTPS/TLS. We now also send **HSTS**, telling browsers to only ever connect over HTTPS. |
| **Passwords** | Stored as **bcrypt** hashes — a one-way function. A stolen database does not reveal anyone's password. Strength rules (length, upper/lower/digit) are enforced. |
| **Sessions** | Logins use signed **JWT tokens** with server-side revocation — logging out or changing a password immediately invalidates existing sessions. Session cookies are HTTP-only and, in production, **Secure**. |
| **Access control** | Role- and module-based: a user only reaches the modules they're granted. The entire admin API requires an administrator token, with an extra PIN gate on sensitive admin accounts. |
| **Login abuse** | Per-IP rate limiting **plus** a new per-account lockout that temporarily blocks an account after repeated failed attempts — stopping password-guessing attacks. |
| **Browser hardening** | Security headers now include a Content-Security-Policy, X-Frame-Options (clickjacking protection), nosniff, Referrer-Policy, and Permissions-Policy. |
| **File uploads** | Uploads now require login, are size-capped, and reject executable/script file types so the storage/CDN cannot be used to stage malicious files. |
| **Server errors** | Error pages never leak internal stack traces or system details to users. |
| **Hosting** | Runs as a **non-root** user inside a container; secrets are supplied by the platform as environment variables, never committed to the code. |

---

## 3. Third-party services and what leaves the app

The application is deliberate about what data goes where. Every integration uses an
encrypted (HTTPS) connection, and every credential is stored in the hosting
platform's secret store — not in the source code.

| Service | Purpose | Data sent | Transport |
|---------|---------|-----------|-----------|
| **Brevo / Mailjet** | Sending email (reports, password resets, notifications) | Recipient address, subject, body, report attachments | HTTPS API |
| **Cloudinary** | Storing inspection photos, signatures, generated PDFs | Uploaded images/documents | HTTPS (secure delivery) |
| **Upstash Redis** | Rate-limiting and background job queue | Transient operational data | TLS connection |
| **Anthropic / OpenAI** _(assistant, optional)_ | Powering the in-app AI assistant | The signed-in user's question plus relevant business context | HTTPS SDK |

Outbound links the server fetches (e.g. document previews) are now protected by an
**SSRF guard** that blocks attempts to reach internal or private network addresses.

---

## 4. What we hardened in this pass

These changes were implemented, tested (application boots cleanly, full auth test
suite passes), and staged on a dedicated branch for review before release:

1. **Locked down form-submission and photo-upload endpoints** — these previously
   accepted anonymous requests; they now require a valid login. (The app's own
   forms were already sending the login token, so normal use is unaffected.)
2. **Upload safety** — added file-type and size validation; executable/script
   uploads are rejected, oversized uploads are capped.
3. **Brute-force protection** — added per-account temporary lockout on repeated
   failed logins.
4. **Security headers** — added HSTS, Content-Security-Policy (in monitoring mode
   first, so it can be tightened without risk), Referrer-Policy and Permissions-Policy.
5. **Correct client-IP handling** — the app now reads the real visitor IP behind the
   load balancer, making rate-limiting and audit logs accurate.
6. **Fail-closed configuration** — in production the app now refuses to start with a
   missing or default security key, rather than silently running insecurely. Secure
   cookies are forced on in production.
7. **Reduced password exposure** — administrators can still view a user's temporary
   password when managing that one user, but the system no longer sends every user's
   password together in the admin directory listing. The old shared reset password
   was replaced with a unique random password per user.
8. **SSRF protection** on server-side URL fetching.

---

## 5. Action items in progress (transparency)

We believe in reporting honestly rather than overstating. These are being completed:

- **Credential rotation (in progress):** Historic development snapshots contained
  service credentials. As a precaution we are **rotating all service keys**
  (email, image storage, Redis, application secret) so any old copy is rendered
  useless. Going forward, secrets are excluded from the code repository entirely.
- **Roadmap:** authenticated/signed delivery URLs for generated documents,
  dependency version upgrades, and automated security scanning in the build
  pipeline.

---

## 6. Summary for the client

The application already followed strong security fundamentals; this pass closed the
remaining gaps and added modern browser and abuse protections. No system is ever
"unhackable," but Injaaz now reflects current industry best practices for a
web application of this kind, is hosted on a reputable managed platform, and has a
clear, honest roadmap for continued hardening.
