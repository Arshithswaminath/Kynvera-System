# Module functional smoke — last run

- **When:** 2026-09-09T11:19:04
- **Target:** `http://127.0.0.1:5002`
- **Artifacts:** `smoke_artifacts/20260909_111829`
- **Totals:** 132 passed, 0 failed, 0 warnings
- **Slow flags:** >5s candidate, >15s high

## Totals by module

| Module | Pass | Fail | Warn | Slow |
|--------|------|------|------|------|
| shell | 9 | 0 | 0 | 0 |
| hr | 45 | 0 | 0 | 0 |
| ticketing | 15 | 0 | 0 | 1 |
| inspection | 10 | 0 | 0 | 0 |
| qhsi | 5 | 0 | 0 | 0 |
| mmr | 6 | 0 | 0 | 0 |
| procurement | 5 | 0 | 0 | 0 |
| assets | 11 | 0 | 0 | 0 |
| admin | 8 | 0 | 0 | 0 |
| files | 3 | 0 | 0 | 0 |
| assistant | 1 | 0 | 0 | 0 |
| notifications | 7 | 0 | 0 | 0 |
| imports | 7 | 0 | 0 | 0 |

## Slow checks

| Status | Module | Check | ms |
|--------|--------|-------|----|
| PASS | ticketing | POST triage-preview | 28977 |

## Failures

None.

## Warnings

None.

## Saved artifacts

| Module | Check | File |
|--------|-------|------|
| hr | GET /hr/api/leave-tracker/export | `hr/xlsx/leave_tracker_export.xlsx` |
| hr | GET /hr/api/leave-tracker/template | `hr/xlsx/leave_log_template.xlsx` |
| hr | GET /hr/api/manpower/export | `hr/xlsx/manpower_export.xlsx` |
| hr | GET /hr/api/manpower/template | `hr/xlsx/manpower_template.xlsx` |
| hr | GET /hr/api/hiring/export | `hr/xlsx/hiring_export.xlsx` |
| hr | GET /hr/api/hiring/import-template | `hr/xlsx/hiring_import_template.xlsx` |
| hr | GET /hr/download-pdf/HR-LEAVE_APPLICATION-31DAA047 | `hr/pdfs/live_HR-LEAVE_APPLICATION-31DAA047.pdf` |
| hr | builder PDF leave_application | `hr/pdfs/hr_leave-application.pdf` |
| hr | builder PDF commencement | `hr/pdfs/hr_commencement.pdf` |
| hr | builder PDF duty_resumption | `hr/pdfs/hr_duty-resumption.pdf` |
| hr | builder PDF passport_release | `hr/pdfs/hr_passport-release.pdf` |
| hr | builder PDF grievance | `hr/pdfs/hr_grievance.pdf` |
| hr | builder PDF visa_renewal | `hr/pdfs/hr_visa-renewal.pdf` |
| hr | builder PDF interview_assessment | `hr/pdfs/hr_interview-assessment.pdf` |
| hr | builder PDF staff_appraisal | `hr/pdfs/hr_staff-appraisal.pdf` |
| hr | builder PDF station_clearance | `hr/pdfs/hr_station-clearance.pdf` |
| hr | builder PDF performance_evaluation | `hr/pdfs/hr_performance-evaluation.pdf` |
| hr | builder PDF contract_renewal | `hr/pdfs/hr_contract-renewal.pdf` |
| hr | builder PDF asset_handover | `hr/pdfs/hr_asset-handover.pdf` |
| ticketing | GET /tickets/api/tickets/export | `ticketing/xlsx/ticket_register.xlsx` |
| ticketing | GET /tickets/api/settings/locations/excel-template | `ticketing/xlsx/location_template.xlsx` |
| ticketing | GET /tickets/api/settings/projects/8/locations/export | `ticketing/xlsx/project_locations.xlsx` |
| ticketing | GET /tickets/TKT-F1CBF74E/pdf | `ticketing/pdfs/TKT-F1CBF74E_report.pdf` |
| ticketing | GET /tickets/TKT-F1CBF74E/invoice | `ticketing/pdfs/TKT-F1CBF74E_invoice.pdf` |
| inspection | builder hvac pdf | `inspection/pdfs/hvac_report.pdf` |
| inspection | builder hvac xlsx | `inspection/xlsx/hvac_report.xlsx` |
| inspection | builder civil pdf | `inspection/pdfs/civil_report.pdf` |
| inspection | builder civil xlsx | `inspection/xlsx/civil_report.xlsx` |
| inspection | builder cleaning pdf | `inspection/pdfs/cleaning_report.pdf` |
| inspection | builder cleaning xlsx | `inspection/xlsx/cleaning_report.xlsx` |
| qhsi | GET /qhsi/api/staff-compliance/import-template | `qhsi/xlsx/staff_compliance_template.xlsx` |
| qhsi | builder QHSI PDF | `qhsi/pdfs/qhsi_inspection.pdf` |
| qhsi | builder QHSI Excel | `qhsi/xlsx/qhsi_inspection.xlsx` |
| mmr | GET /admin/mmr/api/download-report | `mmr/xlsx/mmr_download_report.xlsx` |
| procurement | GET /procurement/api/sample-excel | `procurement/xlsx/procurement_sample.xlsx` |
| procurement | GET /procurement/api/export-excel | `procurement/xlsx/procurement_export.xlsx` |
| assets | GET /assets/api/assets/AST-0014/qr-label.pdf | `assets/pdfs/AST-0014-qr-label.pdf` |
| assets | GET /assets/api/qr-labels.pdf | `assets/pdfs/asset-qr-labels.pdf` |
| admin | GET /api/admin/devices/sample-excel | `admin/xlsx/devices_sample.xlsx` |
| admin | GET /api/admin/technicians/export-template | `admin/xlsx/technicians_template.xlsx` |
| files | GET /files/api/items/99/download | `files/leave_template_from_files.xlsx` |

## All checks

| Status | Module | Check | ms | Detail |
|--------|--------|-------|----|--------|
| PASS | shell | GET /health | 9 | HTTP 200 healthy |
| PASS | shell | PAGE / | 2 | HTTP 200 bytes=49765 |
| PASS | shell | PAGE /login | 1 | HTTP 200 bytes=20346 |
| PASS | shell | POST /api/auth/login | 213 | token present |
| PASS | shell | GET /api/auth/me | 1 | HTTP 200 |
| PASS | shell | PAGE /dashboard | 1 | HTTP 200 bytes=42708 |
| PASS | shell | PAGE /admin | 17 | HTTP 200 bytes=267807 |
| PASS | shell | PAGE /admin/dashboard | 1 | HTTP 200 bytes=267807 |
| PASS | shell | PAGE /dochub | 1 | HTTP 200 bytes=67043 |
| PASS | hr | PAGE /hr/ | 3 | HTTP 200 bytes=68728 |
| PASS | hr | PAGE /hr/my-requests | 6 | HTTP 200 bytes=45139 |
| PASS | hr | PAGE /hr/pending-review | 2 | HTTP 200 bytes=85821 |
| PASS | hr | PAGE /hr/approved-forms | 1 | HTTP 200 bytes=31687 |
| PASS | hr | PAGE /hr/hiring | 2 | HTTP 200 bytes=41821 |
| PASS | hr | PAGE /hr/leave-tracker | 2 | HTTP 200 bytes=57948 |
| PASS | hr | PAGE /hr/employee-list | 2 | HTTP 200 bytes=42377 |
| PASS | hr | PAGE /hr/manpower-tracker | 2 | HTTP 200 bytes=50746 |
| PASS | hr | PAGE /hr/leave-application-form | 13 | HTTP 200 bytes=92179 |
| PASS | hr | PAGE /hr/commencement-form | 6 | HTTP 200 bytes=50915 |
| PASS | hr | PAGE /hr/duty-resumption-form | 7 | HTTP 200 bytes=72728 |
| PASS | hr | PAGE /hr/contract-renewal-form | 5 | HTTP 200 bytes=48002 |
| PASS | hr | PAGE /hr/performance-evaluation-form | 6 | HTTP 200 bytes=51512 |
| PASS | hr | PAGE /hr/grievance-form | 6 | HTTP 200 bytes=51394 |
| PASS | hr | PAGE /hr/interview-assessment-form | 4 | HTTP 200 bytes=42920 |
| PASS | hr | PAGE /hr/passport-release-form | 5 | HTTP 200 bytes=43780 |
| PASS | hr | PAGE /hr/staff-appraisal-form | 5 | HTTP 200 bytes=49704 |
| PASS | hr | PAGE /hr/station-clearance-form | 5 | HTTP 200 bytes=45135 |
| PASS | hr | PAGE /hr/visa-renewal-form | 4 | HTTP 200 bytes=40386 |
| PASS | hr | PAGE /hr/asset-handover-form | 6 | HTTP 200 bytes=56256 |
| PASS | hr | GET /hr/api/notifications/unread-count | 3 | HTTP 200 |
| PASS | hr | GET /hr/api/hiring/candidates | 11 | HTTP 200 |
| PASS | hr | GET /hr/api/leave-tracker/employees | 9 | HTTP 200 |
| PASS | hr | GET /hr/api/leave-tracker/export | 65 | HTTP 200 48263 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/leave-tracker/template | 17 | HTTP 200 11143 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/manpower/export | 42 | HTTP 200 22657 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/manpower/template | 19 | HTTP 200 16485 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/hiring/export | 34 | HTTP 200 12665 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/hiring/import-template | 15 | HTTP 200 9544 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | POST /hr/api/submit (leave) | 1476 | HTTP 200 |
| PASS | hr | GET /hr/api/my-submissions | 14 | HTTP 200 |
| PASS | hr | GET /hr/download-pdf/HR-LEAVE_APPLICATION-31DAA047 | 34 | HTTP 200 13142 bytes ctype=application/pdf |
| PASS | hr | builder PDF leave_application | 0 | 13932 bytes |
| PASS | hr | builder PDF commencement | 0 | 13407 bytes |
| PASS | hr | builder PDF duty_resumption | 0 | 12960 bytes |
| PASS | hr | builder PDF passport_release | 0 | 13703 bytes |
| PASS | hr | builder PDF grievance | 0 | 15593 bytes |
| PASS | hr | builder PDF visa_renewal | 0 | 13051 bytes |
| PASS | hr | builder PDF interview_assessment | 0 | 14933 bytes |
| PASS | hr | builder PDF staff_appraisal | 0 | 14065 bytes |
| PASS | hr | builder PDF station_clearance | 0 | 14312 bytes |
| PASS | hr | builder PDF performance_evaluation | 0 | 15598 bytes |
| PASS | hr | builder PDF contract_renewal | 0 | 16067 bytes |
| PASS | hr | builder PDF asset_handover | 0 | 12624 bytes |
| PASS | hr | HR PDF builders complete | 693 | 12 PDFs |
| PASS | ticketing | PAGE /tickets/ | 5 | HTTP 200 bytes=51590 |
| PASS | ticketing | PAGE /tickets/list | 4 | HTTP 200 bytes=87562 |
| PASS | ticketing | PAGE /tickets/new | 3 | HTTP 200 bytes=205942 |
| PASS | ticketing | PAGE /tickets/drafts | 2 | HTTP 200 bytes=39303 |
| PASS | ticketing | PAGE /tickets/settings | 2 | HTTP 200 bytes=178946 |
| PASS | ticketing | GET /tickets/api/options | 32 | HTTP 200 |
| PASS | ticketing | GET /tickets/api/settings/projects | 5 | HTTP 200 |
| PASS | ticketing | GET /tickets/api/tickets/export | 18 | HTTP 200 8591 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | ticketing | GET /tickets/api/settings/locations/excel-template | 12 | HTTP 200 10182 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | ticketing | GET /tickets/api/settings/projects/8/locations/export | 12 | HTTP 200 10182 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | ticketing | POST /tickets/api/tickets (create) | 11 | HTTP 201 |
| PASS | ticketing | PAGE /tickets/TKT-F1CBF74E | 6 | HTTP 200 bytes=184538 |
| PASS | ticketing | GET /tickets/TKT-F1CBF74E/pdf | 8 | HTTP 200 13306 bytes ctype=application/pdf |
| PASS | ticketing | GET /tickets/TKT-F1CBF74E/invoice | 9 | HTTP 200 3672 bytes ctype=application/pdf |
| PASS | ticketing | POST triage-preview | 28977 | HTTP 200 |
| PASS | inspection | PAGE /inspection/ | 6 | HTTP 200 bytes=22705 |
| PASS | inspection | PAGE /inspection/form | 71 | HTTP 200 bytes=240521 |
| PASS | inspection | GET /inspection/dropdowns | 2 | HTTP 200 |
| PASS | inspection | builder hvac pdf | 0 | 16784 bytes |
| PASS | inspection | builder hvac xlsx | 0 | 133401 bytes |
| PASS | inspection | builder civil pdf | 0 | 13448 bytes |
| PASS | inspection | builder civil xlsx | 0 | 133016 bytes |
| PASS | inspection | builder cleaning pdf | 0 | 13461 bytes |
| PASS | inspection | builder cleaning xlsx | 0 | 133015 bytes |
| PASS | inspection | HVAC/Civil/Cleaning builders | 84 | 3 PDF + 3 Excel |
| PASS | qhsi | PAGE /qhsi/ | 5 | HTTP 200 bytes=27810 |
| PASS | qhsi | GET /qhsi/api/stats | 2 | HTTP 200 |
| PASS | qhsi | GET /qhsi/api/staff-compliance/import-template | 14 | HTTP 200 8405 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | qhsi | builder QHSI PDF | 9 | 19962 bytes |
| PASS | qhsi | builder QHSI Excel | 0 | 5215 bytes |
| PASS | mmr | PAGE /admin/mmr/ | 2 | HTTP 200 bytes=250394 |
| PASS | mmr | PAGE /admin/mmr-chargeable | 7 | HTTP 200 bytes=94761 |
| PASS | mmr | GET /admin/mmr/api/current-upload | 229 | HTTP 200 |
| PASS | mmr | GET /admin/mmr/api/automation-status | 2 | HTTP 200 |
| PASS | mmr | POST /admin/mmr/api/upload (cafm_sample.xlsx) | 10 | HTTP 200 {'dashboard': {'by_client': {'Ajman Municipality': 2}, 'by_contract': {'FM Contract A': 2}, 'by_priority': {'Hi |
| PASS | mmr | GET /admin/mmr/api/download-report | 43 | HTTP 200 54276 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | procurement | PAGE /procurement/ | 2 | HTTP 200 bytes=68818 |
| PASS | procurement | PAGE /procurement/materials | 3 | HTTP 200 bytes=50109 |
| PASS | procurement | GET /procurement/api/materials | 5 | HTTP 200 |
| PASS | procurement | GET /procurement/api/sample-excel | 12 | HTTP 200 8548 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | procurement | GET /procurement/api/export-excel | 10 | HTTP 200 7117 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | assets | PAGE /assets/ | 5 | HTTP 200 bytes=63826 |
| PASS | assets | PAGE /assets/executive | 9 | HTTP 200 bytes=32251 |
| PASS | assets | PAGE /assets/list | 1 | HTTP 200 bytes=32756 |
| PASS | assets | PAGE /assets/map | 1 | HTTP 200 bytes=34110 |
| PASS | assets | PAGE /assets/new | 16 | HTTP 200 bytes=46472 |
| PASS | assets | GET /assets/api/assets | 2 | HTTP 200 |
| PASS | assets | PAGE /assets/AST-0014 | 31 | HTTP 200 bytes=35786 |
| PASS | assets | GET /assets/api/assets/AST-0014 | 2 | HTTP 200 |
| PASS | assets | GET /assets/api/assets/AST-0014/qr-label.pdf | 6 | HTTP 200 6703 bytes ctype=application/pdf |
| PASS | assets | GET /assets/api/qr-labels.pdf | 62 | HTTP 200 72956 bytes ctype=application/pdf |
| PASS | assets | GET /assets/api/kpis | 2 | HTTP 200 |
| PASS | admin | PAGE /admin/devices | 7 | HTTP 200 bytes=94121 |
| PASS | admin | PAGE /admin/team-management | 9 | HTTP 200 bytes=156138 |
| PASS | admin | PAGE /admin/bd | 1 | HTTP 200 bytes=183655 |
| PASS | admin | PAGE /admin/knowledge-base | 3 | HTTP 200 bytes=50124 |
| PASS | admin | PAGE /admin/personal-progress | 3 | HTTP 200 bytes=42548 |
| PASS | admin | GET /api/admin/users | 4 | HTTP 200 |
| PASS | admin | GET /api/admin/devices/sample-excel | 12 | HTTP 200 8436 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | admin | GET /api/admin/technicians/export-template | 12 | HTTP 200 8333 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | files | PAGE /files/ | 6 | HTTP 200 bytes=29095 |
| PASS | files | POST save-from-module leave/template | 21 | HTTP 200 |
| PASS | files | GET /files/api/items/99/download | 2 | HTTP 200 11142 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | assistant | POST /api/assistant/chat | 1038 | HTTP 200 |
| PASS | notifications | GET /hr/api/notifications | 16 | HTTP 200 |
| PASS | notifications | GET /hr/api/notifications/unread-count | 7 | HTTP 200 |
| PASS | notifications | PAGE /admin/email-notifications | 4 | HTTP 200 bytes=267807 |
| PASS | notifications | GET /api/admin/email-logs | 5 | HTTP 200 |
| PASS | notifications | GET /api/admin/notification-config | 3 | HTTP 200 |
| PASS | notifications | GET /api/admin/users | 4 | HTTP 200 |
| PASS | notifications | GET edit-otp/status (no send) | 3 | HTTP 200 |
| PASS | imports | POST /hr/api/hiring/import (preview) | 29 | HTTP 200: {'create_names': [], 'errors': [], 'has_id_conflicts': False, 'message': 'Import preview ready', 'needs_confir |
| PASS | imports | POST /hr/api/leave-tracker/import | 52 | HTTP 200: {'created': 0, 'errors': [], 'logs_created': 27, 'plans_created': 1, 'success': True, 'updated': 194, 'usage_u |
| PASS | imports | POST /hr/api/manpower/import | 27 | HTTP 200: {'created': 22, 'deleted': 0, 'errors': [], 'message': 'Import complete', 'projects_created': 0, 'success': Tr |
| PASS | imports | POST /qhsi/api/staff-compliance/import | 8 | HTTP 200: {'import': {'created_at': '2026-09-09T07:19:03.839260', 'employee_count': 2, 'filename': 'qhsi_staff.xlsx', 'i |
| PASS | imports | POST /procurement/api/import-excel | 153 | HTTP 200: {'errors': [], 'imported': 7, 'message': 'Successfully imported 7 materials', 'success': True, 'total_rows': 7 |
| PASS | imports | GET projects for location import | 17 | HTTP 200 |
| PASS | imports | POST /tickets/api/settings/projects/8/locations/import | 11 | HTTP 200: {'counts': {'base_units_created': 0, 'base_units_updated': 0, 'projects_created': 0, 'properties_created': 1,  |
