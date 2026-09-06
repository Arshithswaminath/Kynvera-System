"""
Email service for sending emails (password resets, notifications)

Send order:
1. Brevo REST — if BREVO_API_KEY is set (HTTPS; works on Render free tier)
2. Mailjet REST — if MAILJET_API_KEY + MAILJET_SECRET_KEY (or Mailjet SMTP host on Render)
3. SMTP fallback — MAIL_SERVER + credentials (IPv4-only for cloud hosts)
"""
import base64
import smtplib
import ssl
import socket
import logging
import os
import re
import mimetypes
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import urlparse
from flask import current_app

import requests

logger = logging.getLogger(__name__)

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"
MAILJET_SEND_URL = "https://api.mailjet.com/v3.1/send"

# Verified Brevo sender for Kynvera transactional mail.
DEFAULT_MAIL_SENDER = 'support@kynvera.net'
# Leftover Render value: Brevo accepts the API call, then rejects the message.
_UNVERIFIED_MAIL_SENDERS = frozenset({
    'contact@kynvera.net',
})

# Gmail/Yahoo/Outlook DMARC rejects third-party API sends that claim these From addresses.
# Brevo/Mailjet often return HTTP 201, then mark the message Error in the dashboard.
_CONSUMER_SENDER_DOMAINS = frozenset({
    'gmail.com', 'googlemail.com', 'yahoo.com', 'yahoo.co.uk',
    'hotmail.com', 'outlook.com', 'live.com', 'icloud.com', 'me.com',
})


def _resolved_mail_sender(app):
    raw = str(
        app.config.get('MAIL_DEFAULT_SENDER') or app.config.get('MAIL_USERNAME') or ''
    ).strip()
    if not raw or raw.lower() in _UNVERIFIED_MAIL_SENDERS:
        if raw:
            logger.warning(
                'MAIL_DEFAULT_SENDER %s is not a verified sender; using %s',
                raw,
                DEFAULT_MAIL_SENDER,
            )
        return DEFAULT_MAIL_SENDER
    return raw


def _api_sender_blocked_reason(mail_sender, provider):
    email = str(mail_sender or '').strip()
    domain = email.rsplit('@', 1)[-1].lower() if '@' in email else ''
    if domain not in _CONSUMER_SENDER_DOMAINS:
        return None
    return (
        f'{provider} cannot send From {email}. Set MAIL_DEFAULT_SENDER to an address '
        f'verified in {provider} on a domain you control (e.g. {DEFAULT_MAIL_SENDER}). '
        'Gmail as From is accepted by the API, then fails as Error in the provider dashboard.'
    )


def _normalize_secret_env(value):
    """Strip whitespace and accidental wrapping quotes (common when pasting into Render)."""
    s = (value or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1].strip()
    return s or None


def _looks_like_mailjet_smtp_host(mail_server):
    if not mail_server:
        return False
    m = mail_server.lower().strip()
    return "mailjet" in m or "in-v3.mailjet" in m


def mailjet_credentials(app=None):
    """API key + secret key (same values as Mailjet SMTP username/password)."""
    a = app if app is not None else current_app._get_current_object()
    k = _normalize_secret_env(
        a.config.get("MAILJET_API_KEY") or os.environ.get("MAILJET_API_KEY")
    )
    s = _normalize_secret_env(
        a.config.get("MAILJET_SECRET_KEY") or os.environ.get("MAILJET_SECRET_KEY")
    )
    if k and s:
        return (k, s)
    if _looks_like_mailjet_smtp_host(a.config.get("MAIL_SERVER")):
        u = _normalize_secret_env(
            a.config.get("MAIL_USERNAME") or os.environ.get("MAIL_USERNAME")
        )
        p = _normalize_secret_env(
            a.config.get("MAIL_PASSWORD") or os.environ.get("MAIL_PASSWORD")
        )
        if u and p:
            return (u, p)
    return None


def _should_send_mailjet_via_rest(app, mj_creds):
    if not mj_creds:
        return False
    if (os.environ.get("MAILJET_USE_REST") or "").lower() in ("1", "true", "yes"):
        return True
    if _normalize_secret_env(
        app.config.get("MAILJET_API_KEY") or os.environ.get("MAILJET_API_KEY")
    ) and _normalize_secret_env(
        app.config.get("MAILJET_SECRET_KEY") or os.environ.get("MAILJET_SECRET_KEY")
    ):
        return True
    if _running_on_render() and _looks_like_mailjet_smtp_host(app.config.get("MAIL_SERVER")):
        return True
    return False


def _running_on_render():
    return (os.environ.get("RENDER") or "").lower() in ("true", "1", "yes")


def brevo_api_key(app=None):
    """Brevo (Sendinblue) API key for HTTPS transactional email."""
    a = app if app is not None else current_app._get_current_object()
    return _normalize_secret_env(
        a.config.get("BREVO_API_KEY") or os.environ.get("BREVO_API_KEY")
    )


def is_email_configured(app=None):
    """True if the app can send mail (Brevo HTTP, Mailjet HTTP, or SMTP)."""
    a = app if app is not None else current_app._get_current_object()
    if brevo_api_key(a):
        return bool(a.config.get("MAIL_DEFAULT_SENDER") or a.config.get("MAIL_USERNAME"))
    mj = mailjet_credentials(a)
    if mj:
        if _should_send_mailjet_via_rest(a, mj):
            return bool(a.config.get("MAIL_DEFAULT_SENDER") or a.config.get("MAIL_USERNAME"))
        return bool(
            a.config.get("MAIL_SERVER")
            and (a.config.get("MAIL_DEFAULT_SENDER") or a.config.get("MAIL_USERNAME"))
        )
    ms = a.config.get("MAIL_SERVER")
    if ms and _looks_like_mailjet_smtp_host(ms) and not mj and _running_on_render():
        return False
    return bool(ms)


def _normalize_socket_timeout(timeout):
    """smtplib passes socket._GLOBAL_DEFAULT_TIMEOUT (sentinel), not None — settimeout needs float or None."""
    if timeout is None:
        return None
    if timeout is socket._GLOBAL_DEFAULT_TIMEOUT:
        return None
    return timeout


def _smtp_socket_ipv4(host, port, timeout):
    """Connect over IPv4 only. Many PaaS hosts (e.g. Render) have no usable IPv6 route to Gmail SMTP."""
    t = _normalize_socket_timeout(timeout)
    port = int(port)
    err = None
    for res in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
        af, socktype, proto, canonname, sa = res
        sock = None
        try:
            sock = socket.socket(af, socktype, proto)
            sock.settimeout(t)
            sock.connect(sa)
            return sock
        except OSError as e:
            err = e
            if sock is not None:
                sock.close()
    if err is not None:
        raise err
    raise OSError(f"No IPv4 address found for {host!r}")


class SMTPIPv4(smtplib.SMTP):
    """SMTP client that connects via IPv4 (avoids errno 101 on broken IPv6 in cloud)."""

    def _get_socket(self, host, port, timeout):
        return _smtp_socket_ipv4(host, port, timeout)


class SMTP_SSL_IPv4(SMTPIPv4, smtplib.SMTP_SSL):
    """SMTP_SSL over IPv4 only."""

    pass


def _iter_attachment_items(attachments):
    """Yield dicts: filename, data, content_type, inline, cid."""
    for item in attachments or []:
        try:
            if isinstance(item, str):
                path = item
                if not os.path.exists(path):
                    logger.warning("Attachment not found: %s", path)
                    continue
                with open(path, "rb") as fh:
                    data = fh.read()
                ctype, _enc = mimetypes.guess_type(path)
                yield {
                    'filename': os.path.basename(path),
                    'data': data,
                    'content_type': ctype or 'application/octet-stream',
                    'inline': False,
                    'cid': None,
                }
            elif isinstance(item, dict):
                data = item.get('content')
                filename = item.get('filename')
                if not data or not filename:
                    continue
                yield {
                    'filename': filename,
                    'data': data,
                    'content_type': item.get('mime_type') or 'application/octet-stream',
                    'inline': bool(item.get('inline')),
                    'cid': item.get('cid'),
                }
        except Exception:
            logger.error("Failed to read attachment", exc_info=True)


def _send_email_brevo_http(app, recipient, subject, body, html_body, cc, attachments, api_key):
    """Send via Brevo transactional REST API (HTTPS)."""
    mail_sender = _resolved_mail_sender(app)
    if not mail_sender:
        logger.error("Brevo: set MAIL_DEFAULT_SENDER to a verified sender in Brevo")
        return False
    blocked = _api_sender_blocked_reason(mail_sender, "Brevo")
    if blocked:
        logger.error("%s", blocked)
        return False

    to_list = recipient if isinstance(recipient, (list, tuple)) else [recipient]
    to_out = [{"email": str(e).strip()} for e in to_list if e and str(e).strip()]
    if not to_out:
        logger.error("Brevo: no valid recipients")
        return False

    payload = {
        "sender": {"name": "Kynvera", "email": str(mail_sender).strip()},
        "to": to_out,
        "subject": subject,
        "textContent": (body or "").rstrip() or " ",
    }
    html = html_body or ''
    att_out = []
    for item in _iter_attachment_items(attachments):
        if item.get('inline') and item.get('cid'):
            # Gmail strips data: URIs; Brevo transactional API does not keep CID
            # Content-ID headers. Hosted HTTPS (or the HTML wordmark) is required.
            continue
        encoded = base64.b64encode(item['data']).decode('ascii')
        att_out.append({'name': item['filename'], 'content': encoded})
    if 'cid:' in html:
        html = re.sub(
            r'<img\b[^>]*src=["\']cid:[^"\']+["\'][^>]*>',
            _html_wordmark(),
            html,
            flags=re.I,
        )
    if html:
        payload["htmlContent"] = html
    if cc:
        cc_list = cc if isinstance(cc, (list, tuple)) else [cc]
        payload["cc"] = [{"email": str(e).strip()} for e in cc_list if e and str(e).strip()]
    if att_out:
        payload["attachment"] = att_out

    try:
        r = requests.post(
            BREVO_SEND_URL,
            json=payload,
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json",
            },
            timeout=120,
        )
        if r.status_code in (200, 201, 202):
            message_id = ""
            try:
                message_id = (r.json() or {}).get("messageId") or ""
            except Exception:
                message_id = ""
            logger.info(
                "Email accepted by Brevo API to %s messageId=%s",
                recipient,
                message_id or "(none)",
            )
            return True
        logger.error("Brevo API HTTP %s: %s", r.status_code, r.text[:4000])
        return False
    except Exception as e:
        logger.error("Brevo API request failed: %s", e, exc_info=True)
        return False


def _send_email_mailjet_http(
    app, recipient, subject, body, html_body, cc, attachments, api_key, secret_key
):
    """Send via Mailjet REST API v3.1 (HTTPS). Works when outbound SMTP is blocked (e.g. Render free)."""
    mail_sender = _resolved_mail_sender(app)
    if not mail_sender:
        logger.error("Mailjet: set MAIL_DEFAULT_SENDER to a verified sender in Mailjet")
        return False
    to_list = recipient if isinstance(recipient, (list, tuple)) else [recipient]
    to_out = []
    for e in to_list:
        if e and str(e).strip():
            to_out.append({"Email": str(e).strip(), "Name": ""})
    if not to_out:
        logger.error("Mailjet: no valid recipients")
        return False
    msg = {
        "From": {"Email": mail_sender.strip(), "Name": "Kynvera"},
        "To": to_out,
        "Subject": subject,
        "TextPart": (body or "").rstrip() or " ",
    }
    if html_body:
        msg["HTMLPart"] = html_body
    if cc:
        cc_list = cc if isinstance(cc, (list, tuple)) else [cc]
        msg["Cc"] = [
            {"Email": str(e).strip(), "Name": ""}
            for e in cc_list
            if e and str(e).strip()
        ]
    att_out = []
    inline_out = []
    for item in _iter_attachment_items(attachments):
        encoded = base64.b64encode(item['data']).decode('ascii')
        if item.get('inline') and item.get('cid'):
            inline_out.append({
                'ContentType': item['content_type'],
                'Filename': item['filename'],
                'ContentID': item['cid'],
                'Base64Content': encoded,
            })
        else:
            att_out.append({
                'ContentType': item['content_type'],
                'Filename': item['filename'],
                'Base64Content': encoded,
            })
    if att_out:
        msg['Attachments'] = att_out
    if inline_out:
        msg['InlinedAttachments'] = inline_out
    payload = {"Messages": [msg]}
    try:
        r = requests.post(
            MAILJET_SEND_URL,
            json=payload,
            auth=(api_key, secret_key),
            timeout=120,
        )
        if r.status_code in (200, 201):
            logger.info("Email sent via Mailjet API to %s", recipient)
            return True
        logger.error("Mailjet API HTTP %s: %s", r.status_code, r.text[:4000])
        return False
    except Exception as e:
        logger.error("Mailjet API request failed: %s", e, exc_info=True)
        return False


EMAIL_LOG_SOURCES = frozenset({
    'inspection', 'hr', 'bd_email', 'mmr', 'ticketing', 'auth', 'other',
})
_BODY_PREVIEW_MAX = 400
_ERROR_MAX = 500


def _join_emails(value):
    if not value:
        return ''
    if isinstance(value, (list, tuple)):
        return ', '.join(str(v).strip() for v in value if v and str(v).strip())
    return str(value).strip()


def _attachment_count(attachments):
    if not attachments:
        return 0
    return len([item for item in attachments if item])


def _normalize_source(source):
    s = (source or 'other').strip().lower()
    return s if s in EMAIL_LOG_SOURCES else 'other'


def _body_preview(body, source):
    if source == 'auth':
        text = (body or '').lower()
        if 'system user has been created' in text or 'account is ready' in text:
            return 'Account created notification'
        if 'login details, sent by an administrator' in text or 'here are your kynvera login details' in text:
            return 'Login details notification'
        if 'account has been activated' in text:
            return 'Account activated notification'
        if 'account has been deactivated' in text:
            return 'Account deactivated notification'
        if 'password has been reset' in text or 'temporary password is:' in text:
            return 'Password reset notification'
        if (
            'updated the password' in text
            or 'password was updated' in text
            or 'password was changed' in text
            or 'account was changed' in text
        ):
            return 'Password updated notification'
        return 'Password reset notification'
    text = ' '.join((body or '').split())
    if len(text) > _BODY_PREVIEW_MAX:
        return text[: _BODY_PREVIEW_MAX - 3] + '...'
    return text


def _record_email_log(
    *,
    recipient,
    subject,
    body,
    cc,
    attachments,
    ok,
    source,
    sent_by_user_id,
    related_id,
    error_message,
):
    """Persist a send attempt. Never raises — logging must not fail the send."""
    try:
        from flask import has_app_context
        if not has_app_context():
            return
        from app.models import EmailLog, db

        src = _normalize_source(source)
        related = str(related_id).strip() if related_id else None
        row = EmailLog(
            status='sent' if ok else 'failed',
            source=src,
            subject=(subject or '')[:500],
            to_emails=_join_emails(recipient)[:2000],
            cc_emails=_join_emails(cc)[:2000],
            sent_by_user_id=sent_by_user_id,
            related_id=(related[:120] if related else None),
            body_preview=_body_preview(body, src)[:500],
            attachment_count=_attachment_count(attachments),
            error_message=(str(error_message)[:_ERROR_MAX] if (error_message and not ok) else None),
        )
        db.session.add(row)
        db.session.commit()
    except Exception as exc:
        logger.warning("Could not record email log: %s", exc)
        try:
            from app.models import db as _db
            _db.session.rollback()
        except Exception:
            pass


def send_email(
    recipient,
    subject,
    body,
    html_body=None,
    cc=None,
    attachments=None,
    source=None,
    sent_by_user_id=None,
    related_id=None,
):
    """
    Send email via Brevo HTTPS, Mailjet HTTPS, or SMTP (see module docstring).

    Optional source / sent_by_user_id / related_id are stored on the admin email log.

    Returns:
        bool: True if sent successfully, False otherwise
    """
    error_message = None
    ok = False
    try:
        ok = bool(_deliver_email(recipient, subject, body, html_body, cc, attachments))
        if not ok:
            error_message = 'Send failed'
    except Exception as e:
        logger.error("Failed to send email: %s", e, exc_info=True)
        error_message = str(e)
        ok = False
    _record_email_log(
        recipient=recipient,
        subject=subject,
        body=body,
        cc=cc,
        attachments=attachments,
        ok=ok,
        source=source,
        sent_by_user_id=sent_by_user_id,
        related_id=related_id,
        error_message=error_message,
    )
    return ok


def _deliver_email(recipient, subject, body, html_body=None, cc=None, attachments=None):
    """
    Send email via Brevo HTTPS, Mailjet HTTPS, or SMTP (see module docstring).

    Returns:
        bool: True if sent successfully, False otherwise
    """
    try:
        app = current_app._get_current_object()

        brevo_key = brevo_api_key(app)
        if brevo_key:
            return _send_email_brevo_http(
                app, recipient, subject, body, html_body, cc, attachments, brevo_key
            )

        mj = mailjet_credentials(app)
        if mj and _should_send_mailjet_via_rest(app, mj):
            return _send_email_mailjet_http(
                app, recipient, subject, body, html_body, cc, attachments, mj[0], mj[1]
            )

        mail_server = app.config.get('MAIL_SERVER')
        mail_port = app.config.get('MAIL_PORT', 587)
        mail_user = app.config.get('MAIL_USERNAME')
        mail_pass = app.config.get('MAIL_PASSWORD')
        mail_use_tls = app.config.get('MAIL_USE_TLS', True)
        mail_sender = _resolved_mail_sender(app) or mail_user or DEFAULT_MAIL_SENDER

        if not mail_server or not mail_port:
            logger.warning(
                "Mail not configured; cannot send email "
                "(set BREVO_API_KEY + MAIL_DEFAULT_SENDER, or Mailjet/SMTP credentials)"
            )
            return False

        if _looks_like_mailjet_smtp_host(mail_server) and _running_on_render() and not mj:
            logger.error(
                "Email: Mailjet on Render needs API credentials. Set MAILJET_API_KEY + "
                "MAILJET_SECRET_KEY + MAIL_DEFAULT_SENDER (HTTPS), or MAIL_USERNAME + "
                "MAIL_PASSWORD with MAIL_SERVER=in-v3.mailjet.com. See docs/EMAIL_SMTP_OPTIONS.md",
            )
            return False

        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = formataddr(("Kynvera", str(mail_sender).strip()))
        if isinstance(recipient, (list, tuple)):
            msg['To'] = ', '.join(recipient)
        else:
            msg['To'] = recipient

        if cc:
            if isinstance(cc, (list, tuple)):
                msg['Cc'] = ', '.join(cc)
            else:
                msg['Cc'] = cc

        if html_body:
            msg.set_content(body)
            msg.add_alternative(html_body, subtype='html')
        else:
            msg.set_content(body)

        html_part = None
        if html_body:
            try:
                for part in msg.walk():
                    if part.get_content_type() == 'text/html':
                        html_part = part
                        break
            except Exception:
                html_part = None

        for item in _iter_attachment_items(attachments):
            try:
                mime_type = item['content_type']
                maintype, subtype = mime_type.split('/', 1)
                if item.get('inline') and item.get('cid') and html_part is not None:
                    html_part.add_related(
                        item['data'],
                        maintype=maintype,
                        subtype=subtype,
                        cid=item['cid'],
                    )
                else:
                    msg.add_attachment(
                        item['data'],
                        maintype=maintype,
                        subtype=subtype,
                        filename=item['filename'],
                    )
            except Exception:
                logger.error("Failed to attach file", exc_info=True)

        if mail_use_tls:
            context = ssl.create_default_context()
            with SMTPIPv4(mail_server, mail_port) as server:
                server.starttls(context=context)
                if mail_user and mail_pass:
                    server.login(mail_user, mail_pass)
                server.send_message(msg)
        else:
            context = ssl.create_default_context()
            with SMTP_SSL_IPv4(mail_server, mail_port, context=context) as server:
                if mail_user and mail_pass:
                    server.login(mail_user, mail_pass)
                server.send_message(msg)

        logger.info("Email sent successfully to %s", recipient)
        return True

    except Exception as e:
        logger.error("Failed to send email: %s", e, exc_info=True)
        return False


def _app_base_url():
    try:
        return (current_app.config.get('APP_BASE_URL') or '').rstrip('/')
    except Exception:
        return ''


def _login_url():
    base = _app_base_url()
    return f'{base}/login' if base else '/login'


_WORDMARK_CID = 'kynvera-wordmark'
_WORDMARK_STATIC = '/static/images/kynvera/kynvera-wordmark.png'
_cloudinary_wordmark_url_cache = None


def _wordmark_path():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, 'static', 'images', 'kynvera', 'kynvera-wordmark.png')
    return path if os.path.isfile(path) else ''


def _is_public_asset_base(url):
    """True when inbox clients (Gmail, Outlook) can fetch this host."""
    try:
        parsed = urlparse((url or '').strip())
    except Exception:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    host = (parsed.hostname or '').lower()
    if not host or host in ('localhost', '127.0.0.1', '::1') or host.endswith('.local'):
        return False
    return True


def _html_wordmark():
    return (
        '<span style="font-family:Arial,Helvetica,sans-serif;font-size:18px;'
        'font-weight:800;color:#ff8e68;letter-spacing:-0.4px;line-height:1;">Kynvera</span>'
    )


def _img_wordmark(src):
    return (
        f'<img src="{_esc(src)}" alt="Kynvera" width="120" '
        'style="display:block;border:0;outline:none;text-decoration:none;'
        'width:120px;max-width:140px;height:auto;">'
    )


def _cloudinary_wordmark_url():
    """Upload the wordmark once and reuse the HTTPS URL (Gmail can fetch this)."""
    global _cloudinary_wordmark_url_cache
    if _cloudinary_wordmark_url_cache is not None:
        return _cloudinary_wordmark_url_cache
    path = _wordmark_path()
    if not path:
        _cloudinary_wordmark_url_cache = ''
        return ''
    try:
        if current_app.config.get('TESTING'):
            _cloudinary_wordmark_url_cache = ''
            return ''
    except Exception:
        pass
    try:
        from app.services.cloudinary_service import init_cloudinary
        import cloudinary.uploader
        if not init_cloudinary():
            _cloudinary_wordmark_url_cache = ''
            return ''
        res = cloudinary.uploader.upload(
            path,
            folder='kynvera',
            public_id='email-wordmark',
            overwrite=True,
            resource_type='image',
            unique_filename=False,
            use_filename=False,
        )
        url = str((res or {}).get('secure_url') or '')
        _cloudinary_wordmark_url_cache = url
        if url:
            logger.info('Hosted email wordmark at %s', url)
        return url
    except Exception:
        logger.warning('Could not host email wordmark on Cloudinary', exc_info=True)
        _cloudinary_wordmark_url_cache = ''
        return ''


def _hosted_wordmark_url():
    try:
        explicit = (current_app.config.get('EMAIL_WORDMARK_URL') or '').strip()
    except Exception:
        explicit = ''
    if _is_public_asset_base(explicit):
        return explicit.rstrip('/')
    base = _app_base_url()
    if _is_public_asset_base(base):
        return f'{base}{_WORDMARK_STATIC}'
    return _cloudinary_wordmark_url()


def _wordmark_inline_attachment():
    path = _wordmark_path()
    if not path:
        return None
    with open(path, 'rb') as fh:
        data = fh.read()
    if not data:
        return None
    return {
        'filename': 'kynvera-wordmark.png',
        'content': data,
        'mime_type': 'image/png',
        'cid': _WORDMARK_CID,
        'inline': True,
    }


def _send_auth_email(user_email, subject, body, html_body):
    attachments = []
    if html_body and f'cid:{_WORDMARK_CID}' in html_body:
        wm = _wordmark_inline_attachment()
        if wm:
            attachments.append(wm)
    return send_email(user_email, subject, body, html_body, source='auth', attachments=attachments)


def _esc(value):
    import html as html_lib
    return html_lib.escape(str(value or ''), quote=True)


def _logo_html():
    hosted = _hosted_wordmark_url()
    if hosted:
        return _img_wordmark(hosted)
    try:
        if brevo_api_key():
            # Brevo transactional API drops CID images; Gmail also strips data: URIs.
            return _html_wordmark()
    except Exception:
        pass
    if _wordmark_path():
        return _img_wordmark(f'cid:{_WORDMARK_CID}')
    return _html_wordmark()


def branded_kynvera_html(*, greeting, paragraphs, extra_html='', cta_url='', cta_label='Open in Kynvera'):
    """Public wrapper for the Outlook-safe Kynvera transactional card."""
    return _branded_auth_html(
        title='',
        greeting=greeting,
        paragraphs=paragraphs,
        extra_html=extra_html,
        cta_url=cta_url,
        cta_label=cta_label,
    )


def _branded_auth_html(*, title, greeting, paragraphs, extra_html='', cta_url='', cta_label='Sign in'):
    """Outlook-safe Kynvera card with the coral wordmark (no header bar)."""
    del title
    logo_html = _logo_html()

    paras = ''.join(
        f'<p style="margin:0 0 12px 0;font-family:Arial,Helvetica,sans-serif;'
        f'font-size:15px;line-height:1.55;color:#1c1917;">{p}</p>'
        for p in paragraphs
    )
    cta_html = ''
    if cta_url:
        cta_html = f'''
<tr>
  <td style="padding:8px 32px 0 32px;">
    <table cellpadding="0" cellspacing="0" border="0">
      <tr>
        <td bgcolor="#ff8e68" style="background-color:#ff8e68;border-radius:8px;">
          <a href="{_esc(cta_url)}"
             style="display:inline-block;padding:11px 22px;font-family:Arial,Helvetica,sans-serif;
                    font-size:14px;font-weight:bold;color:#ffffff;text-decoration:none;">{_esc(cta_label)}</a>
        </td>
      </tr>
    </table>
  </td>
</tr>'''

    return f'''<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background-color:#f4f1ee;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f4f1ee" style="background-color:#f4f1ee;">
  <tr>
    <td align="center" style="padding:28px 16px;">
      <table width="600" cellpadding="0" cellspacing="0" border="0" bgcolor="#ffffff"
             style="width:600px;max-width:600px;background-color:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #efe7e2;">
        <tr>
          <td style="padding:28px 32px 8px 32px;">
            {logo_html}
          </td>
        </tr>
        <tr>
          <td style="padding:8px 32px 8px 32px;">
            <p style="margin:0 0 16px 0;font-family:Arial,Helvetica,sans-serif;font-size:22px;
                      font-weight:800;color:#191b23;">{greeting}</p>
            {paras}
            {extra_html}
          </td>
        </tr>
        {cta_html}
        <tr>
          <td style="padding:20px 32px 28px 32px;">
            <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.5;color:#8a7e78;">
              Kynvera · All operations. One platform.<br>Do not reply to this email.
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>'''


def send_account_created_email(user_email, username, full_name=None, temp_password=None):
    """Welcome email after an admin creates a system user. Includes username; temp password only if generated."""
    display = (full_name or '').strip() or username
    login_url = _login_url()
    subject = 'Your Kynvera account is ready'

    lines = [
        f'Hello {display},',
        'A Kynvera system user has been created for you.',
        f'Your username is: {username}',
    ]
    if temp_password:
        lines.append(f'Your temporary password is: {temp_password}')
        lines.append('Sign in and change this password the first time you log in.')
    else:
        lines.append('Sign in with the password your administrator set for this account.')
    lines.extend(['If you were not expecting this account, contact your administrator.', 'Kynvera'])
    body = '\n\n'.join(lines)

    extra = (
        '<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="margin:4px 0 16px 0;background-color:#fff8f5;border:1px solid #fde4d8;border-radius:10px;">'
        '<tr><td style="padding:14px 16px;font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#191b23;">'
        f'<strong>Username</strong><br><span style="font-size:16px;">{_esc(username)}</span>'
    )
    if temp_password:
        extra += (
            f'<br><br><strong>Temporary password</strong><br>'
            f'<code style="font-size:15px;">{_esc(temp_password)}</code>'
        )
    extra += '</td></tr></table>'

    html_body = _branded_auth_html(
        title='Account created',
        greeting=f'Welcome, {_esc(display)}',
        paragraphs=[
            'A Kynvera system user has been created for you. Use the username below to sign in.',
            'If you were not expecting this account, contact your administrator.',
        ],
        extra_html=extra,
        cta_url=login_url,
        cta_label='Sign in to Kynvera',
    )
    return _send_auth_email(user_email, subject, body, html_body)


def send_password_updated_email(user_email, username, *, by_admin=False, full_name=None):
    """Notify the user that their password was changed. Never includes the new password."""
    display = (full_name or '').strip() or username
    subject = 'Your Kynvera password was updated'
    if by_admin:
        intro = 'An administrator updated the password on your Kynvera account.'
        next_step = 'Sign in with the password they shared with you, then change it if you were asked to. If you did not expect this, contact your administrator immediately.'
    else:
        intro = 'The password on your Kynvera account was changed.'
        next_step = 'If you did not make this change, contact your administrator immediately.'

    body = f"""Hello {display},

{intro}

{next_step}

Kynvera
"""
    html_body = _branded_auth_html(
        title='Password updated',
        greeting=f'Hello {_esc(display)}',
        paragraphs=[intro, next_step],
        cta_url=_login_url(),
        cta_label='Sign in to Kynvera',
    )
    return _send_auth_email(user_email, subject, body, html_body)


def send_account_status_email(user_email, username, *, is_active, full_name=None):
    """Notify the user that an admin activated or deactivated their account."""
    display = (full_name or '').strip() or username
    if is_active:
        subject = 'Your Kynvera account has been activated'
        intro = 'Your Kynvera account has been activated. You can sign in again.'
        next_step = 'If you did not expect this, contact your administrator.'
        title = 'Account activated'
        cta_url = _login_url()
        cta_label = 'Sign in to Kynvera'
    else:
        subject = 'Your Kynvera account has been deactivated'
        intro = 'Your Kynvera account has been deactivated. You will not be able to sign in until an administrator turns it back on.'
        next_step = 'If you think this was a mistake, contact your administrator.'
        title = 'Account deactivated'
        cta_url = ''
        cta_label = ''

    body = f"""Hello {display},

{intro}

{next_step}

Kynvera
"""
    html_body = _branded_auth_html(
        title=title,
        greeting=f'Hello {_esc(display)}',
        paragraphs=[intro, next_step],
        cta_url=cta_url,
        cta_label=cta_label,
    )
    return _send_auth_email(user_email, subject, body, html_body)


def send_password_reset_email(user_email, username, temp_password):
    """Send password reset email with temporary password."""
    subject = 'Your Kynvera account password has been reset'
    body = f"""Hello {username},

Your password has been reset by an administrator.

Your temporary password is: {temp_password}

Please log in and change your password immediately for security.

If you did not request this password reset, please contact support immediately.

Kynvera
"""
    extra = (
        '<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="margin:4px 0 16px 0;background-color:#fff8f5;border:1px solid #fde4d8;border-radius:10px;">'
        '<tr><td style="padding:14px 16px;font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#191b23;">'
        f'<strong>Username</strong><br>{_esc(username)}<br><br>'
        f'<strong>Temporary password</strong><br><code style="font-size:15px;">{_esc(temp_password)}</code>'
        '</td></tr></table>'
    )
    html_body = _branded_auth_html(
        title='Password reset',
        greeting=f'Hello {_esc(username)}',
        paragraphs=[
            'Your password has been reset by an administrator.',
            'Sign in with the temporary password below and change it immediately.',
            'If you did not request this reset, contact support immediately.',
        ],
        extra_html=extra,
        cta_url=_login_url(),
        cta_label='Sign in to Kynvera',
    )
    return _send_auth_email(user_email, subject, body, html_body)


def send_forgot_password_email(user_email, username, token, full_name=None):
    """Self-service password reset link (expires in one hour)."""
    display = (full_name or '').strip() or username
    base = _app_base_url()
    reset_path = f'/reset-password?token={token}'
    reset_url = f'{base}{reset_path}' if base else reset_path
    subject = 'Reset your Kynvera password'
    body = f"""Hello {display},

We received a request to reset the password on your Kynvera account.

Open this link to choose a new password (it expires in one hour):
{reset_url}

If you did not request this, you can ignore this email. Your password will not change.

Kynvera
"""
    html_body = _branded_auth_html(
        title='Reset your password',
        greeting=f'Hello {_esc(display)}',
        paragraphs=[
            'We received a request to reset the password on your Kynvera account.',
            'This link expires in one hour. If you did not request a reset, ignore this email — your password will not change.',
        ],
        cta_url=reset_url,
        cta_label='Choose a new password',
    )
    return _send_auth_email(user_email, subject, body, html_body)


def send_login_details_email(user_email, username, password, full_name=None):
    """Admin-triggered email with username and the stored password. Redacted in email logs."""
    display = (full_name or '').strip() or username
    login_url = _login_url()
    subject = 'Your Kynvera login details'
    body = f"""Hello {display},

Here are your Kynvera login details, sent by an administrator.

Your username is: {username}
Your password is: {password}

Sign in with these details. If you did not expect this email, contact your administrator.

Kynvera
"""
    extra = (
        '<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="margin:4px 0 16px 0;background-color:#fff8f5;border:1px solid #fde4d8;border-radius:10px;">'
        '<tr><td style="padding:14px 16px;font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#191b23;">'
        f'<strong>Username</strong><br><span style="font-size:16px;">{_esc(username)}</span>'
        f'<br><br><strong>Password</strong><br>'
        f'<code style="font-size:15px;">{_esc(password)}</code>'
        '</td></tr></table>'
    )
    html_body = _branded_auth_html(
        title='Login details',
        greeting=f'Hello {_esc(display)}',
        paragraphs=[
            'Here are your Kynvera login details, sent by an administrator.',
            'Sign in with the username and password below. If you did not expect this email, contact your administrator.',
        ],
        extra_html=extra,
        cta_url=login_url,
        cta_label='Sign in to Kynvera',
    )
    return _send_auth_email(user_email, subject, body, html_body)


def send_admin_edit_otp_email(user_email, code, full_name=None):
    """6-digit code to authorize editing an administrator profile. Do not log the code."""
    display = (full_name or '').strip() or 'Administrator'
    subject = 'Kynvera administrator verification code'
    body = f"""Hello {display},

A verification code was requested to edit this administrator account in Kynvera.

Your code is: {code}

It expires in 10 minutes. If you did not request this, contact your administrator.

Kynvera
"""
    extra = (
        '<table cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="margin:4px 0 16px 0;background-color:#fff8f5;border:1px solid #fde4d8;border-radius:10px;">'
        '<tr><td style="padding:14px 16px;font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#191b23;">'
        '<strong>Verification code</strong><br>'
        f'<code style="font-size:22px;letter-spacing:0.12em;font-weight:700;">{_esc(code)}</code>'
        '</td></tr></table>'
    )
    html_body = _branded_auth_html(
        title='Administrator verification',
        greeting=f'Hello {_esc(display)}',
        paragraphs=[
            'A verification code was requested to edit this administrator account in Kynvera.',
            'Enter the code below in Manage profile. It expires in 10 minutes. If you did not request this, contact your administrator.',
        ],
        extra_html=extra,
        cta_url='',
        cta_label='',
    )
    return _send_auth_email(user_email, subject, body, html_body)
