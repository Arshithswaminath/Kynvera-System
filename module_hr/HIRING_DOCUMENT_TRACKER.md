# Hiring Document Tracker — Context for Cursor

## What we're building

A new sub-module inside the existing HR module (`module_hr/`) — a dashboard that tracks, per candidate/new-hire, which onboarding documents have been collected and lets HR upload the missing ones. This is a document checklist + tracking system, not a form builder.

## Where it fits

- Backend: extend `module_hr/` (blueprint `hr_bp` in `module_hr/routes.py`, `Blueprint('hr', __name__, template_folder='templates')`). Add routes/views for this feature in a new file, e.g. `module_hr/hiring_documents.py`, and register them on `hr_bp` (or a nested blueprint) rather than bloating `routes.py`.
- Templates: new HTML files under `module_hr/templates/`, following existing naming (`hr_hiring_dashboard.html`, `hr_hiring_candidate_detail.html`), consistent with siblings like `hr_dashboard.html`, `hr_pending_review.html`.
- Models: add to `app/models.py` following existing conventions (see `File` and `DocHubDocument` classes for the established pattern of storing uploads: `filename`, `stored_path`/`file_path`, `cloud_url`, `file_type`, `uploaded_at`, plus a `to_dict()` method).
- File storage: reuse `app/services/cloudinary_service.py` (already used for signatures/uploads) rather than introducing a new storage mechanism. Local fallback path pattern already exists via `UPLOADS_DIR` / `GENERATED_DIR` in `config.py`.

## Documents to track per candidate

1. Passport copy (colour)
2. Emirates ID copy (colour)
3. Photograph — white background, PDF
4. PCC (Police Clearance Certificate) — attested
5. Education certificate — PDF

Each has its own accepted format (mostly PDF, first two are colour scans/images) — validate file type per document type on upload, don't use one generic rule.

## Proposed data model

```
Candidate
  id, full_name, role/position, department, phone, email,
  status (Not Started / In Progress / Complete — derived from documents),
  created_at, updated_at

HiringDocument
  id, candidate_id (FK -> Candidate),
  doc_type (enum: passport, emirates_id, photograph, pcc, education_certificate),
  filename, stored_path, cloud_url, file_type, file_size,
  status (Missing / Uploaded / Attested-Pending / Verified) — PCC needs an "attested" sub-state,
  uploaded_at, uploaded_by (FK -> User)
```

Completion % / "3 of 5" progress = count of `HiringDocument` rows with status Uploaded (or Verified) per candidate against the fixed 5 doc types.

## Dashboard UI (web, iOS-inspired)

- Light mode, clean Apple-style aesthetic (SF Pro-like, rounded cards, soft shadows, iOS system blue #007AFF accents) — consistent visual language with the rest of the app but not literally an iOS app screen; this is a web dashboard page.
- Left sidebar or top nav consistent with existing HR module navigation.
- Main list: one row/card per candidate — avatar/initials, name, role, progress bar or "3/5" badge, status pill (green Complete / orange In Progress / gray Not Started).
- Search + filter (All / Pending / Complete).
- Click a candidate → detail view with the 5-document checklist, each row showing upload state and an "Upload" button (or "Uploaded ✓" / "Re-upload").
- Upload should support drag-and-drop and mobile camera capture (the app also ships via Capacitor for iOS/Android per `package.json`, so keep the upload widget touch-friendly).

## Reference image prompts

See `HR_Hiring_Dashboard_Image_Prompt.md` in the repo root for AI image-generation prompts describing this dashboard's look (list screen + candidate detail/upload screen) — use as a visual reference when building the actual templates/CSS, not as literal assets.

## Open questions to resolve during implementation

- Who can upload/verify documents — HR only, or can the candidate self-upload via a shared link?
- Does "attested" for PCC need its own verification step/approval, or is it just a checkbox HR ticks after manually confirming the physical stamp?
- Should this tie into an existing `Submission`/workflow signoff pattern already used elsewhere in `module_hr` (e.g. `hr_routed_signoffs.py`), or stay a simpler standalone checklist?
