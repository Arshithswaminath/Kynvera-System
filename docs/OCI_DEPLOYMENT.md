# Injaaz on Oracle Cloud (OCI) Free Tier

Runbook for a **small Always Free VM** with **persistent disk** (boot volume and optional block volume) so `GENERATED_DIR` (MMR saved reports, uploads, etc.) survives reboots and redeploys **unlike** ephemeral PaaS filesystems.

**Official references:** [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/) · [Always Free resources](https://docs.oracle.com/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)

---

## 1. What you get on Always Free (typical)

- **Ampere A1 Flex** (ARM): up to **4 OCPUs and 24 GB RAM** total per region (split across one or more VMs).
- **AMD Micro** instances: two small VMs (1 GB RAM each) — enough for experiments only.
- **Block storage** within Always Free caps (see OCI docs for current GiB limits).

Pick **Ubuntu 22.04** (or 24.04) **aarch64** for ARM, or **x86_64** for Micro shapes.

---

## 2. One-time: account, network, instance

1. **Sign up** for Oracle Cloud (credit card for verification; Always Free resources should not incur charges if you stay within limits — confirm on Oracle’s pricing/free pages).
2. **Create a compartment** (e.g. `Injaaz-Prod` or `Injaaz-Test`).
3. **Networking → VCN** → create with **Start VCN Wizard** (include public subnet + Internet Gateway).
4. **Compute → Instances → Create**:
   - **Image:** Canonical Ubuntu (match **ARM64** if you chose an Ampere shape).
   - **Shape:** `VM.Standard.A1.Flex` (ARM) — e.g. **1 OCPU, 6 GB RAM** for one node, or smaller if you split the quota.
   - **VCN / subnet:** your public subnet.
   - **Public IPv4:** assign.
   - **SSH keys:** paste your public key (you need the matching private key to log in).
5. **Security list** (subnet or NSG): allow inbound:
   - **TCP 22** — SSH (restrict source to **your IP** when possible).
   - **TCP 80 / 443** — HTTP/HTTPS after you put Nginx in front (see below).
6. Wait until the instance is **Running**, note the **public IP**.

---

## 3. Persistent data directory (this app)

The app stores generated files under **`GENERATED_DIR`** (see `config.py`). On a VM, use a **dedicated path on disk**, not inside a throwaway container layer without a bind mount.

**Recommended (boot volume — persists across reboots):**

```bash
sudo mkdir -p /var/injaaz/generated
sudo chown "$USER:$USER" /var/injaaz/generated
```

Set **`GENERATED_DIR=/var/injaaz/generated`** in your environment (`.env` or systemd `Environment=`).

**Optional — separate block volume:** In OCI **Block Storage**, create and **attach** a volume to the instance, mount it e.g. on `/var/injaaz`, add to `/etc/fstab`, then use `GENERATED_DIR=/var/injaaz/generated` as above. Use this if you want data on a volume you can snapshot or move independently of the OS disk.

---

## 4. Database

Production expects **PostgreSQL** via **`DATABASE_URL`** when `FLASK_ENV=production` (see `config.py` / `Injaaz.py`).

**Options:**

| Approach | Notes |
|----------|--------|
| **OCI Autonomous Database** (Free Tier where available) | Managed; more setup in console. |
| **PostgreSQL in Docker** on the same VM | Simple for testing; backup the data volume. |
| **External managed Postgres** (Neon, Supabase, Render Postgres, etc.) | Set `DATABASE_URL` to the provider’s URL. |

Use a strong URL and restrict network access (OCI **Security Lists** / **NSGs** + DB firewall rules).

---

## 5. Deploy the app (Python + Gunicorn, no Docker)

Example for Ubuntu on the VM:

```bash
sudo apt update && sudo apt install -y git python3-venv python3-dev build-essential libpq-dev nginx
cd /opt
sudo git clone <YOUR_REPO_URL> injaaz-app
sudo chown -R "$USER:$USER" injaaz-app
cd injaaz-app
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-prods.txt
```

Create `/opt/injaaz-app/.env` (or use `/etc/injaaz.env` with restricted permissions) with at least:

- `FLASK_ENV=production`
- `SECRET_KEY`, `JWT_SECRET_KEY`
- `DATABASE_URL=postgresql+psycopg2://...` (or dialect your app expects)
- `GENERATED_DIR=/var/injaaz/generated`
- `APP_BASE_URL=https://your-domain-or-ip`
- Cloudinary, Redis (optional), Mailjet/Brevo, etc. — same ideas as `RENDER_DEPLOYMENT_PHASES.md`

**Systemd** unit (example path — adjust user and paths):

`/etc/systemd/system/injaaz.service`:

```ini
[Unit]
Description=Injaaz Gunicorn
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/injaaz-app
EnvironmentFile=/opt/injaaz-app/.env
ExecStart=/opt/injaaz-app/.venv/bin/gunicorn wsgi:app \
  --bind 127.0.0.1:8000 --workers 1 --threads 4 --timeout 300 --worker-class gthread
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now injaaz
```

**Nginx** reverse proxy to `127.0.0.1:8000`, then **Certbot** for Let’s Encrypt on your domain.

---

## 6. Deploy with Docker (optional)

The repo `Dockerfile` runs Gunicorn on `$PORT`. If you use Docker, **bind-mount** persistent data:

```bash
docker run -d --name injaaz \
  -p 8000:5000 \
  -v /var/injaaz/generated:/data/generated \
  -e GENERATED_DIR=/data/generated \
  -e PORT=5000 \
  --env-file /opt/injaaz.env \
  your-image:tag
```

Without `-v`, files written inside the container are lost when you recreate the container.

---

## 7. Checklist before you rely on it

- [ ] `GENERATED_DIR` points at a **host path** that is **not** wiped on deploy (see above).
- [ ] `DATABASE_URL` points to a **durable** Postgres; run `flask db upgrade` if you use migrations.
- [ ] Firewall: only **22 / 80 / 443** (or your chosen ports) from trusted sources.
- [ ] **Backups:** OCI **boot volume / block volume backups** or snapshots on a schedule; test restore once.
- [ ] **Secrets:** never commit `.env`; use OCI **Vault** or restricted files for production.

---

## 8. Cost note

Always Free resources are **free within documented limits**. If you create paid SKUs, extra regions, or exceed free storage/compute, charges apply. Monitor **Billing → Cost analysis** in OCI.

---

## Related in this repo

- `RENDER_DEPLOYMENT_PHASES.md` — same env vars (minus Render-specific disk wording).
- `docs/EMAIL_SMTP_OPTIONS.md` — Brevo vs Mailjet vs SMTP.
- `config.py` — `GENERATED_DIR` from environment.
