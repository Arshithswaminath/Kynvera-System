# AI-Powered FM Capabilities — Full Implementation Plan for Injaaz

**Audience:** Cursor / whoever picks up this file to start building.
**Goal:** Cover all 11 sections of the client's vendor compliance checklist (`AI_FM_Vendor_Compliance_Checklist.docx`) and the capabilities described in their BRD (`AI_Powered_FM_BRD_With_Examples.docx`), inside the existing Injaaz codebase — not just the AI pieces, all 11.

Read this whole file before writing code. It tells you what already exists, what's missing, what order to build in, and what "done" looks like for each of the 11 sections.

---

## 1. What the client actually asked for

The client sent two documents to evaluate FM software vendors (including us). The checklist has 11 sections, each scored per requirement as **OOTB** (out of the box) / **Configuration** / **Customization** / **Not Available**:

1. Asset Management
2. AI Asset Intelligence
3. Intelligent Work Orders
4. Executive Dashboard
5. AI Assistant
6. Predictive Analytics
7. GIS & Smart Maps
8. Mobile Application
9. Integration
10. Security
11. Digital Twin + AI

Only about a third of this is actually AI (sections 2, 3, 5, 6, part of 11). The rest is real product engineering — dashboards, maps, mobile, integrations, security hardening. This plan covers all 11 so nothing gets silently dropped, but it's honest about which parts are AI/Claude work and which are plain engineering, because that changes both how you build it and what you tell the client about maturity (OOTB vs. Customization).

---

## 2. Current state of the Injaaz codebase (verified, not assumed)

Injaaz is a Flask app (`Injaaz.py` entrypoint, blueprints per module) backed by SQLAlchemy models in `app/models.py`, with feature modules under `module_*/`, and an existing native mobile shell via Capacitor (`capacitor.config.ts`, `android/` folder present).

**Already exists and is directly reusable:**

- `module_assistant/` — working RAG + LLM assistant, already wired to the **Anthropic API** (`llm.py`). Config already in `config.py`: `ANTHROPIC_API_KEY`, `ASSISTANT_LLM_PROVIDER` (default `claude`), `ASSISTANT_LLM_MODEL` (default `claude-haiku-4-5`), `ASSISTANT_LLM_ENABLED`. Also has `rag.py`, `knowledge.py`, `tools.py`, `intents.py`, `responses.py`.
- `Ticket` model (`app/models.py:1131`) — the work order object: `priority`, `status`, `technician_id`, `assigned_to_id`, `supervisor_id`, category/fault/service fields, cost fields, full lifecycle. **No SLA field, no asset link, no auto-assignment today.**
- `Technician` model (`app/models.py:1465`) — roster with `specialization`, `department`, `status`.
- `User` model (`app/models.py:22`) — has `role` (`admin`/`user`) **plus a set of per-module boolean access flags** (`access_hvac`, `access_civil`, `access_cleaning`, `access_hr`, `access_procurement_module`, `access_business_development`, `access_report_generation`, `access_submitted_forms`, `access_ticketing`, `access_qhsi`, etc. — see `to_dict()` around line 137). This **is** Injaaz's existing RBAC — coarse (feature-flag style, not fine-grained permissions/roles-per-object), but real and functioning.
- `AuditLog` model (`app/models.py:388`) — audit logging already exists at the model level; verify actual coverage (which actions write to it) before assuming it's complete.
- `module_hvac_mep/`, `module_civil/`, `module_cleaning/`, `module_qhsi/` — domain modules with generators/routes but **no formal Asset model**.
- `Device` model (`app/models.py:446`) — IT device management (laptops/desktops), **not** an FM asset registry. Don't conflate with the new `Asset` model.
- Mobile: `capacitor.config.ts` + `android/` directory already present — this is a real native shell, not just a package.json aspiration. Check what's already wired (camera/filesystem/network plugins are in `package.json` dependencies) before assuming greenfield.
- Dashboards: dashboard-related code exists scattered per module (`module_qhsi/routes.py`, `app/admin/routes.py`, `app/workflow/routes.py`, `module_procurement/routes.py`, `module_inspection/routes.py`, `module_mmr/`, etc.) — these are per-module dashboards, not a unified FM executive dashboard with the specific KPIs the client wants (Building Health %, Warranty Status, Budget Utilization). Confirm what each shows before building a new one from scratch; there may be reusable aggregation queries already written.

**Verified as NOT existing — confirmed by search, not assumed:**

- No `Asset` model at all.
- No SLA field or auto-assignment logic on `Ticket`.
- No failure prediction / RUL / forecasting of any kind.
- No GIS/mapping library anywhere in the codebase (no Leaflet, Mapbox, geojson, or lat/lng-driven map view — a couple of HR asset-handover form fields matched "location"-type searches but are unrelated to GIS).
- No SSO or MFA implementation (only coincidental substring matches on unrelated code — verified, not present).
- No ERP/BMS/SCADA integration code (same — searches turned up unrelated coincidental matches, nothing real).
- No 3D/digital twin or IoT ingestion of any kind.

**Action before writing any code:** re-run these searches against the live repo before starting each phase below — this snapshot may drift as other work lands on the codebase.

---

## 3. How each of the 11 sections should actually be solved

| # | Section | Real nature | Approach |
|---|---|---|---|
| 1 | Asset Management | Plain data model | New `Asset` model + CRUD. Not AI. |
| 2 | AI Asset Intelligence | Predictive ML (ideally), Claude estimate as v1 | Claude-reasoned estimate first; label clearly as heuristic; real model later once historical data exists. |
| 3 | Intelligent Work Orders | LLM reasoning + thin rules layer | Claude call returns structured priority/SLA/technician/parts; human confirms. |
| 4 | Executive Dashboard | Plain aggregation queries | SQL aggregates across Asset/Ticket. Only "why did costs increase" narrative uses Claude. |
| 5 | AI Assistant | LLM | Extend existing `module_assistant`. |
| 6 | Predictive Analytics | Predictive ML (ideally), Claude estimate as v1 | Same treatment as #2. |
| 7 | GIS & Smart Maps | Plain frontend (mapping library) | Not AI. New workstream — needs a map library (Leaflet/Mapbox) and Asset lat/lng fields (add to Phase 0's Asset model). |
| 8 | Mobile Application | Plain mobile engineering | Not AI. Build on the existing Capacitor/`android` shell rather than starting fresh. |
| 9 | Integration | Plain systems integration | Not AI. Needs client discovery first (see Phase 7) — cannot be scoped precisely without knowing their ERP/BMS/SCADA systems. |
| 10 | Security | Plain infra | Not AI. Existing role/access-flag system is a starting point, not a finished RBAC/SSO/MFA stack. |
| 11 | Digital Twin + AI | 3D/IoT engineering + Claude reasoning | 3D/IoT is a major separate workstream; the "AI Recommendations" sub-item reuses the Phase 2/3 Claude reasoning layer once live sensor data exists. |

---

## 4. Build phases, in order

Each phase should be usable and demoable on its own. Phases 0–3 are prerequisites for almost everything else (Asset data, the Claude-calling pattern) — build those first regardless of which of the 11 sections you tackle next.

### Phase 0 — Data foundation (blocks nearly everything below)
1. Add an `Asset` model to `app/models.py` (style: `to_dict()`, timestamps, indexed lookups — follow `Device`/`Ticket` conventions).
   - Fields for section 1 (Asset Management): `asset_id` (unique, e.g. `AST-0001`), `qr_code`, `name`, `asset_type`, `building`, `floor`, `room`, `manufacturer`, `model`, `serial_number`, `installation_date`, `warranty_expiry`, `purchase_cost`, `maintenance_cost_total`, `status`, `health_score` (0-100), `image_urls`, `created_at`/`updated_at`.
   - Also add `latitude`/`longitude` now (even if unused until Phase 5, GIS) — cheaper to add alongside the rest of the model than as a separate migration later.
   - Add nullable `asset_id` FK to `Ticket` for work-order-to-asset rollups.
2. Migration under `migrations/` following the repo's existing hand-written script pattern (see `add_technicians_table.py` — no Alembic in use, confirm before assuming otherwise).
3. Basic CRUD routes + minimal admin UI for Assets.

**Done when:** an admin can create/view/edit an Asset (with location fields), and a Ticket can optionally link to one.

### Phase 1 — Intelligent Work Orders (section 3)
1. New module `module_ai_triage/` (or extend `module_ticketing/`) with `triage_ticket(ticket) -> dict`.
2. Claude prompt input: ticket title/description/property/zone + linked asset history + active technician roster (name, specialization, status). Output: strict JSON — `priority`, `sla_hours`, `technician_id`, `required_parts`, `reasoning`.
3. Wire into ticket creation: pre-fill suggested fields, supervisor confirms/edits before final (human-in-the-loop in v1 — don't auto-apply).
4. Log every call (inputs, raw response, human decision) to a new `TicketTriageLog` table — audit trail + future training data.

**Done when:** creating a ticket shows an AI-suggested priority/SLA/technician/parts list a supervisor can accept or edit in one click.

### Phase 2 — AI Assistant extensions (section 5)
1. Extend `module_assistant/intents.py` / `tools.py` with FM-specific intents: "which building has the most failures," "show all critical assets," "why did maintenance costs increase this month" (aggregate + Claude narrates), "generate [month] maintenance report (PDF)" (reuse existing PDF/report pattern already in the repo — check `DOCUMENT_GENERATION_STATUS.md` and existing report modules before building a new PDF pipeline).
2. Reuse `llm.py`'s existing Claude client — don't instantiate a second one.

**Done when:** the existing assistant chat answers FM-specific questions using live Asset/Ticket data.

### Phase 3 — Predictive layer (sections 2 and 6)
1. v1 (ship fast): Claude-reasoned failure-probability and RUL estimate from an asset's full history (installation date, maintenance/ticket history, manufacturer/model), same structured-JSON pattern as Phase 1.
2. Tag every v1 prediction with `method: "llm_estimate"` so it's distinguishable from a future `method: "trained_model"` output — matters for both engineering honesty and what you tell the client.
3. v2 (real model, once 6-12 months of historical ticket/asset data exists): survival analysis or gradient-boosted regression per asset type, starting with HVAC/chillers (richest existing domain data via `module_hvac_mep`).
4. Reuse the same v1 approach for section 6's budget/failure/spare-parts forecasting — same Claude pattern, different prompt.

**Done when:** an asset detail page shows failure probability and RUL with a visible estimate-vs-model-backed label; a forecasting endpoint returns budget/failure/spare-parts projections the same way.

### Phase 4 — Executive Dashboard (section 4)
1. Audit existing per-module dashboard code (`module_qhsi/routes.py`, `app/admin/routes.py`, `app/workflow/routes.py`, `module_procurement/routes.py`, `module_inspection/routes.py`, `module_mmr/`) to identify what aggregation logic already exists and can be reused rather than rewritten.
2. Build a single FM executive dashboard endpoint/view aggregating: Building Health % (derived from Asset `health_score` averages per building), Asset Status counts, Open Work Orders (Ticket status counts), Budget (sum of Ticket/Asset cost fields), Contract status (only if a Contracts model exists or is added — check first), Warranty Status (from Asset `warranty_expiry`), and a KPI summary block.
3. Plain SQL aggregation — no AI, except an optional Claude-generated one-line narrative summarizing the numbers ("costs rose 12% this month, mainly HVAC") reusing the Phase 2 assistant pattern.

**Done when:** a single dashboard view shows all the KPIs listed in the checklist's Executive Dashboard section, backed by real Asset/Ticket data.

### Phase 5 — GIS & Smart Maps (section 7)
**Requires client discovery first:** confirm whether they expect an embedded interactive map (Leaflet/Mapbox on web) or something deeper (live GPS tracking infra) — this changes scope significantly.
1. Add a mapping library (Leaflet is the lower-cost default; Mapbox if the client wants nicer styling and you're fine with its usage-based pricing) to the frontend.
2. Plot Assets on the map using the `latitude`/`longitude` fields added in Phase 0.
3. Building Status overlay: color-code buildings/pins by aggregate health/open-ticket count (reuses Phase 4's aggregation logic).
4. Live Technician Location: only build this if the client actually needs real-time tracking — it requires a location-reporting mechanism from the mobile app (Phase 6) and a live data feed (e.g. periodic ping stored against `Technician`/`User`), which is a meaningfully bigger scope item than a static map. Confirm before committing.

**Done when:** an interactive map shows assets and buildings with status color-coding; live technician tracking only if explicitly scoped after discovery.

### Phase 6 — Mobile Application (section 8)
Build on the existing Capacitor + `android/` shell — this is not greenfield.
1. Confirm current state: which Capacitor plugins (`@capacitor/camera`, `@capacitor/filesystem`, `@capacitor/network`, etc., already in `package.json`) are actually wired into working screens versus just installed.
2. Offline Mode: local queue/cache for ticket submissions and asset lookups when `@capacitor/network` reports offline, syncing on reconnect.
3. QR Scanner: for Asset QR codes (added in Phase 0) — scan to pull up asset detail/create a ticket against it.
4. Photo Capture: via `@capacitor/camera`, likely already partially supported through existing ticket image upload (`TicketImage` model) — confirm before rebuilding.
5. Digital Signature: check if this already exists (ticket closing flow has `close_signature`/`ops_close_signature` base64 fields in the `Ticket` model — likely already implemented for web; confirm mobile parity).
6. Push Notifications: needs a push provider (Firebase Cloud Messaging for Android, APNs for iOS) wired through Capacitor — not yet present, needs building.
7. iOS: only `android/` currently exists — confirm with the team whether iOS is in scope for this client before adding `@capacitor/ios` build targets.

**Done when:** field technicians can work offline, scan asset QR codes, capture photos/signatures, and receive push notifications on the existing mobile shell.

### Phase 7 — Integration (section 9)
**Requires client discovery first** — "ERP," "Finance," "HR," "BMS," "SCADA" are placeholders until you know the client's actual systems (e.g. SAP vs. Oracle vs. a homegrown BMS). Do not build speculative connectors.
1. Build one generic, reusable integration layer first: an outbound webhook/API-push mechanism (ticket/asset events → configurable external endpoint) and an inbound REST API with API-key auth for the "API Integration" checklist row specifically — this row you can actually build without client specifics, since it's just "expose our own API," and it's the one integration item you can mark closer to OOTB/Configuration honestly.
2. For ERP/Finance/HR/GIS/BMS/SCADA: schedule a discovery call with the client to identify actual systems and required data flows before scoping further work — each is effectively a separate mini-project once the target system is known.

**Done when:** Injaaz exposes a documented, authenticated API and can push events to a configurable webhook; ERP/BMS/SCADA connectors are scoped only after discovery, not built speculatively.

### Phase 8 — Security (section 10)
1. Audit current state precisely: `User.role` (admin/user) + per-module `access_*` boolean flags is real but coarse RBAC — no per-object permissions, no role hierarchy beyond admin/user. Confirm with the team whether the client's checklist expects finer-grained RBAC (e.g. "can edit assets in Building A but not Building B") — that would be new work, not a config change.
2. Audit Logs: `AuditLog` model exists — verify actual write coverage (which actions log, which don't) rather than assuming it's complete; extend where thin.
3. Single Sign-On: not present — would need an OAuth2/SAML provider integration (e.g. Azure AD/Okta, likely relevant for a corporate FM client) — scope only if the client names a specific IdP.
4. Multi-Factor Authentication: not present — TOTP-based MFA (e.g. `pyotp`) is the standard lightweight addition to an existing username/password flow.
5. Data Encryption: verify what's already true (HTTPS in transit, DB-level encryption at rest depends on hosting — check deployment config/`Dockerfile`/hosting provider settings) before claiming or denying this on the checklist.

**Done when:** you can answer, with evidence from the code (not assumption), exactly what RBAC/audit/SSO/MFA/encryption currently covers, and MFA is implemented if the client requires it.

### Phase 9 — Digital Twin + AI (section 11)
The largest, lowest-priority-to-start section — sequence it last.
1. 3D Building Model + Room Status Visualization: requires either a pre-built 3D asset (e.g. from BIM/CAD files if the client can provide them) or a simplified 2D floor-plan-with-status-overlay as a cheaper first version — recommend proposing the 2D version first and confirming whether the client actually requires true 3D before committing to that scope.
2. IoT Integration: requires a live sensor data feed from the client's building systems — another discovery-dependent item like Phase 7's integrations; no sensors exist to integrate with until the client specifies what hardware/protocol they use (BACnet, MQTT, etc.).
3. AI Recommendations: once room/asset status data exists (from either the 2D or 3D version) and optionally live sensor data, reuse the Phase 2/3 Claude reasoning pattern to generate recommendations exactly like the BRD's example ("Room 2.105 turns RED... AI recommendations").

**Done when:** at minimum, a 2D floor-plan view shows live room/asset status with drill-down to assets/work orders/history, with Claude-generated recommendations layered on top — true 3D and IoT only if scoped after client discovery.

---

## 5. Claude integration pattern (use this everywhere Claude is involved: Phases 1, 2, 3, 4's narrative, 9)

Don't call the Anthropic SDK ad hoc in each module. Add one shared helper — extend `module_assistant/llm.py` with a generic structured-output function:

```python
def generate_structured(system_prompt: str, user_content: str, model: str = None) -> dict:
    """Call Claude and parse a strict-JSON response. Raises on malformed output."""
    # Reuse _get_claude_client() from module_assistant/llm.py
    # Instruct Claude to return ONLY valid JSON, no prose, no markdown fences.
    # Validate with json.loads + a schema check (pydantic or manual) before
    # trusting the output downstream.
```

Rules for every Claude call in this project:
- **Always request structured JSON** for anything feeding a DB write or UI form (triage, predictions). Free text only for assistant chat replies.
- **Always validate** the JSON against an expected schema before using it — a malformed `technician_id` must never silently corrupt a ticket.
- **Always keep a human in the loop** for anything that changes ticket state, cost, or assignment in v1.
- **Log inputs and outputs** for every structured call — audit trail and future training data.
- Use `claude-haiku-4-5` (already the default in `config.py`) for triage/classification-style calls; only escalate to a larger model if haiku proves insufficiently accurate in testing.

---

## 6. What "done" looks like for the vendor checklist, per section

| # | Section | Honest checklist answer once built |
|---|---|---|
| 1 | Asset Management | Available (OOTB/Configuration) — plain CRUD, no caveats needed. |
| 2 | AI Asset Intelligence | Available with Configuration (Claude-backed, human-reviewed) → Customization/OOTB once v2 real model ships. |
| 3 | Intelligent Work Orders | Available with Configuration — Claude-backed, human confirms before final. |
| 4 | Executive Dashboard | Available (OOTB/Configuration) — plain aggregation. |
| 5 | AI Assistant | Available with Configuration — needs API key + prompt tuning. |
| 6 | Predictive Analytics | Available with Customization until v2 real model. |
| 7 | GIS & Smart Maps | Available with Customization — new workstream, scope depends on live-tracking requirement. |
| 8 | Mobile Application | Available with Configuration/Customization — builds on existing shell, some features (push, offline) need new work. |
| 9 | Integration | API Integration row: Configuration. ERP/Finance/HR/BMS/SCADA rows: Not Available until client discovery defines scope — do not overclaim here. |
| 10 | Security | RBAC/Audit Logs: Configuration (exists, coarse). SSO/MFA: Not Available until built. Encryption: verify actual hosting config before answering. |
| 11 | Digital Twin + AI | Not Available (3D/IoT) until scoped; 2D + AI recommendations version: Customization. |

Never mark anything "Available Out-of-the-Box" if it depends on the Anthropic API key, prompt tuning, or a review workflow to function, and never mark integration/security rows as available before they're actually built — this checklist is likely being compared line-by-line against competitors, and overclaiming here is the fastest way to lose credibility in a live demo.

---

## 7. Immediate next steps for whoever starts this

1. Re-verify this document's codebase assumptions — they may have drifted.
2. Start with Phase 0 (Asset model + migration, including lat/lng for later GIS use) — nearly everything else depends on it.
3. Confirm `ANTHROPIC_API_KEY` is actually populated in the target environment (`config.py:111` has the slot; verify the value, not just its presence).
4. Build Phase 1 end-to-end for one ticket type (HVAC first — richest existing domain module) before generalizing.
5. Schedule client discovery conversations before starting Phase 5 (GIS live-tracking scope), Phase 7 (integration targets), and Phase 9 (3D vs. 2D, IoT hardware/protocol) — these three phases cannot be accurately scoped from the BRD/checklist alone.
