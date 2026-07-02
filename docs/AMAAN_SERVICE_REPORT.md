# Amaan Service Report — Digital Form & PDF

This document describes the **Amaan Service Report** feature implemented in the Ticketing module. It mirrors the paper template shared as:

- **Blank template:** `Service Report (maintenance, installation, rectification, others)_ITEM No. 1.pdf`
- **Filled example:** `4024_001.pdf` (SRN shown as `46958 (Need to change)` — SRN is **editable** in the app)

The PDF output is **client-facing**: it reproduces the paper layout and does **not** include internal pricing, margins, or finance-only fields.

---

## Overview

| Layer | Purpose |
|-------|---------|
| **Web form** | Mobile-first card UI for technicians/supervisors to review, edit, and save report data |
| **JSON storage** | Editable fields persisted on `Ticket.service_report_data` |
| **PDF export** | ReportLab builder that renders the paper layout for print / client handoff |
| **Auto-fill** | Ticket, materials, manpower, and workflow data pre-populate fields marked **Auto** |

**Entry point:** Ticket detail → **Service Report** button → `/tickets/<ticket_id>/service-report`

---

## Paper template → digital mapping

### Header

| Paper field | App / PDF source | Notes |
|-------------|------------------|-------|
| AMAAN logo | `static/icons/AMAAN Logo - Edited.png` (fallbacks in PDF builder) | PDF header only |
| **SERVICE REPORT** title | Fixed in PDF | |
| Tel / Fax / P.O. Box / email / website | Fixed Amaan contact lines in PDF | |
| **SRN** (Service Report Number) | `Ticket.service_report_no` | Auto-assigned on first open; **editable** in UI and PATCH API |

**SRN assignment:** Sequential integer starting from `max(existing SRN) + 1`, or `46001` if none exist.

---

### General information grid

| Paper field | JSON key | Auto-fill source | Editable in UI |
|-------------|----------|------------------|----------------|
| Customer | `client_name` | `TicketProject.client_name` → `ticket.project` | Yes (Auto badge) |
| Job No | `job_no` | `ticket.ticket_id` | Yes (Auto badge) |
| Page | — | PDF only: `1 of 1` | — |
| Site Name | `site_name` | `ticket.property_name` | Yes (Auto badge) |
| Location | `location` | `zone / sub_zone / base_unit` joined | Yes (Auto badge) |
| Engineer / Technician | `technician_name` | `ticket.technician` or `ticket.assigned_to` | Yes (Auto badge) |
| Date | `service_date` | Earliest manpower `work_date` → `site_attended_at` → `created_at` | Yes (Auto badge) |
| Time Arrive (Hrs / Mns) | `time_arrive.h`, `time_arrive.m` | `ticket.site_attended_at` | Yes (Auto badge) |
| Time Left (Hrs / Mns) | `time_left.h`, `time_left.m` | `ticket.work_completed_at` | Yes (Auto badge) |
| Travel Time | `travel_time.h`, `travel_time.m` | Empty by default | Yes |
| Total | `total_time.h`, `total_time.m` | Computed from Arrive ↔ Left; overridable | Yes (Auto badge) |

---

### Fire Alarm System

| Paper field | JSON path |
|-------------|-----------|
| Qty | `fire_alarm.qty` |
| Type | `fire_alarm.type` |
| Make | `fire_alarm.make` |
| No. of Zones / Loops | `fire_alarm.zones_loops` |

All manual entry in the web form; empty checkboxes/lines on PDF if blank.

---

### Fire Fighting System (checkboxes)

| Paper label | JSON key |
|-------------|----------|
| Fire Extinguisher | `fire_fighting.fire_extinguisher` |
| Gas Suppression | `fire_fighting.gas_suppression` |
| Hose Reel | `fire_fighting.hose_reel` |
| Kitchen Hood | `fire_fighting.kitchen_hood` |
| Sprinkler | `fire_fighting.sprinkler` |
| Wet / Dry Riser | `fire_fighting.wet_dry_riser` |
| Fire Pump Set | `fire_fighting.fire_pump_set` |
| Others | `fire_fighting.others` + `fire_fighting.others_text` |

PDF renders ☑ / ☐ Unicode checkboxes.

---

### Type of Job (single choice)

| Paper option | JSON `job_type` | Auto-suggest rule |
|--------------|-----------------|-------------------|
| Maintenance | `maintenance` | Fault type in PPM / Corrective / Annual Inspection |
| Installation | `installation` | Installation, Commissioning, Testing & Certification, Upgrade |
| Rectification | `rectification` | Ticket linked to inspection notification (`source_inspection_notif_id`) |
| Others | `others` | Remaining fault types; free text in `job_type_other` |

PDF uses ● / ○ markers for selected type.

---

### Comments

| Paper field | JSON key | Auto-fill |
|-------------|----------|-----------|
| Comments (ruled area) | `comments` | `technician_resolution_notes` + `service_report_notes` merged |

---

### Parts Used / Parts Required

| Paper table | Source |
|-------------|--------|
| **Parts Used** | `TicketMaterial` rows (name, `notes` as specification, quantity) — read-only in UI, **Auto from materials** |
| **Parts Required** | `parts_required[]` — `{ part, specification, qty }` — user adds/removes rows in UI |

PDF pads each table to at least 5 rows with blank lines.

---

### Customer Remarks

| Paper field | JSON key |
|-------------|----------|
| Customer Remarks (3 lines) | `customer_remarks` |

---

### Signatures

| Paper block | Ticket fields | Web form behaviour |
|-------------|---------------|-------------------|
| **Customer** — Name, Signature, Mobile No | `client_signed_by`, `client_signature`, `client_mobile` | Canvas signature pad + POST client-sign if not yet signed |
| **Engineer / Technician** — Name, Signature, ID No | `close_signed_by`, `close_signature`, `technician_id_no` | Technician signature from work-order close; ID editable and saved to `technician_id_no` |

Client sign API also accepts `client_mobile` and persists it on the ticket.

---

## Web form structure (8 cards)

The UI in `module_ticketing/templates/ticket_service_report.html` is organized as:

1. **Job Details** — Customer, Job No, Site, Location, Technician, Date  
2. **Time On Site** — Arrive, Left, Travel, Total (auto-compute on arrive/left change)  
3. **System Details** — Fire Alarm fields + Fire Fighting toggles  
4. **Type of Job** — Radio group + Others text  
5. **Work Comments** — Multi-line textarea  
6. **Parts** — Parts Used (from materials) + editable Parts Required rows  
7. **Customer Remarks** — Textarea  
8. **Sign-off** — Customer canvas / read-only signed state; Technician ID + close signature  

**Sticky footer:** Save · PDF · Print · status message

Fields with an **Auto** badge are pre-filled but remain editable; saves overwrite the JSON blob.

---

## Data model

### `Ticket` columns

```text
service_report_no    INTEGER UNIQUE   -- SRN (auto + editable)
service_report_data  TEXT             -- JSON blob of form fields
client_mobile        VARCHAR(40)      -- Customer mobile (sign-off + PDF)
technician_id_no     VARCHAR(80)      -- Technician ID on PDF footer
client_signature     TEXT             -- base64 data-URL
client_signed_by     VARCHAR(160)
client_signed_at     DATETIME
close_signature      TEXT             -- Technician/supervisor close signature
close_signed_by      VARCHAR(160)
service_report_notes TEXT             -- Merged into comments auto-fill
```

### `service_report_data` JSON schema (effective shape)

```json
{
  "client_name": "",
  "job_no": "",
  "site_name": "",
  "location": "",
  "technician_name": "",
  "service_date": "YYYY-MM-DD",
  "time_arrive": { "h": 9, "m": 30 },
  "time_left": { "h": 11, "m": 0 },
  "travel_time": { "h": null, "m": null },
  "total_time": { "h": 1, "m": 30 },
  "fire_alarm": {
    "qty": "", "type": "", "make": "", "zones_loops": ""
  },
  "fire_fighting": {
    "fire_extinguisher": false,
    "gas_suppression": false,
    "hose_reel": false,
    "kitchen_hood": false,
    "sprinkler": false,
    "wet_dry_riser": false,
    "fire_pump_set": false,
    "others": false,
    "others_text": ""
  },
  "job_type": "maintenance|installation|rectification|others",
  "job_type_other": "",
  "comments": "",
  "parts_required": [
    { "part": "", "specification": "", "qty": 1 }
  ],
  "customer_remarks": "",
  "client_mobile": "",
  "technician_id_no": ""
}
```

Merge rule (`merge_service_report_data`): saved user values win; auto-fill only fills keys the user has never set (empty/null). Nested objects (`fire_alarm`, `fire_fighting`, time dicts) merge key-by-key.

---

## API routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/tickets/<ticket_id>/service-report` | Render web form (JWT required) |
| `GET` | `/tickets/api/tickets/<ticket_id>/service-report-data` | Load merged JSON + assign SRN if missing + `parts_used` from materials |
| `PATCH` | `/tickets/api/tickets/<ticket_id>/service-report-data` | Save form payload; validates SRN uniqueness and `job_type` |
| `GET` | `/tickets/<ticket_id>/service-report/pdf` | Stream generated PDF |
| `POST` | `/tickets/api/tickets/<ticket_id>/client-sign` | Save client signature, name, optional mobile |

### PATCH validation highlights

- `service_report_no` — positive integer, unique across tickets  
- `job_type` — one of `maintenance`, `installation`, `rectification`, `others`  
- `parts_required` — empty rows stripped before save  
- `client_mobile`, `technician_id_no` — also copied to top-level ticket columns when provided  

---

## Source files

| File | Role |
|------|------|
| `module_ticketing/service_report.py` | Auto-fill, job-type mapping, merge logic, SRN assignment |
| `module_ticketing/service_report_pdf_builder.py` | ReportLab PDF matching paper layout |
| `module_ticketing/templates/ticket_service_report.html` | Card-based web form + JS save/load/signature |
| `module_ticketing/routes.py` | Page, API, PDF, client-sign handlers |
| `module_ticketing/templates/ticket_detail.html` | Service Report button on ticket detail |
| `app/models.py` | `Ticket` columns listed above |

---

## PDF layout sections (ReportLab)

Built in order by `build_service_report_pdf()`:

1. **Header** — Logo \| SERVICE REPORT \| contact + SRN  
2. **General info** — 3×3 grid (Customer/Job/Page; Site/Location; Tech/Date/Time mini-table)  
3. **Systems + job type** — Three columns: Fire Alarm \| Fire Fighting checklist \| Type of Job  
4. **Comments** — Label + ruled lines (min 12 lines)  
5. **Parts** — Side-by-side Parts Used \| Parts Required tables  
6. **Customer remarks** — Label + 3 ruled lines  
7. **Signatures** — Customer \| Technician two-column block with embedded signature images  

Footer: `Page N of M — Amaan Facilities Management`

---

## Access control

- Form page and PDF: `_can_access_ticket_docs(user, ticket)`  
- PATCH save: ticket visible to user via `_api_forbid_unless_ticket_visible`  
- Client sign: users with ticketing access on visible tickets  

---

## Workflow notes

- **Service Report** replaces the old work-order PDF link on ticket detail for client-facing documentation.  
- Finance may use Service Report + Team's Invoice after supervisor verification.  
- Technician signature on the PDF comes from the **close / verify** workflow (`close_signature`), not from the Service Report form itself.  
- Internal pricing, profit margin, and GM/Finance gates remain on the ticket record — **not** on the Service Report PDF.

---

## Testing checklist

- [ ] Open Service Report on a ticket with materials → Parts Used populated  
- [ ] Auto fields (Customer, Job No, Site, times) pre-fill; edit and Save → reload persists overrides  
- [ ] Change SRN → Save; duplicate SRN on another ticket returns error  
- [ ] Select job type + fire fighting checkboxes → PDF reflects selections  
- [ ] Add Parts Required rows → appear on PDF  
- [ ] Client signature submit → PDF shows name, mobile, signature image  
- [ ] Mobile layout: sticky save bar, 44px touch targets, single-column grids  
- [ ] Print preview hides nav and save bar  

---

## Reference PDFs (shared)

These files were the design source; they are **not** stored in the repository:

| File | Use |
|------|-----|
| `Service Report (maintenance, installation, rectification, others)_ITEM No. 1.pdf` | Blank paper layout |
| `4024_001.pdf` | Example filled report; confirmed SRN must be user-editable |

---

*Last updated: June 2026 — matches implementation in Ticketing module Service Report feature.*
