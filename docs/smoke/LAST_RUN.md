# Module functional smoke — last run

- **When:** 2026-09-05T21:09:34
- **Target:** `http://127.0.0.1:5002`
- **Artifacts:** `smoke_artifacts/20260905_210926`
- **Totals:** 117 passed, 0 failed, 0 warnings
- **Slow flags:** >5s candidate, >15s high

## Totals by module

| Module | Pass | Fail | Warn | Slow |
|--------|------|------|------|------|
| shell | 9 | 0 | 0 | 0 |
| hr | 44 | 0 | 0 | 0 |
| ticketing | 15 | 0 | 0 | 0 |
| inspection | 10 | 0 | 0 | 0 |
| qhsi | 5 | 0 | 0 | 0 |
| mmr | 6 | 0 | 0 | 0 |
| procurement | 5 | 0 | 0 | 0 |
| assets | 11 | 0 | 0 | 0 |
| admin | 8 | 0 | 0 | 0 |
| files | 3 | 0 | 0 | 0 |
| assistant | 1 | 0 | 0 | 0 |

## Slow checks

None above the slow threshold.

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
| hr | GET /hr/download-pdf/HR-LEAVE_APPLICATION-972F27E4 | `hr/pdfs/live_HR-LEAVE_APPLICATION-972F27E4.pdf` |
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
| ticketing | GET /tickets/TKT-56C43507/pdf | `ticketing/pdfs/TKT-56C43507_report.pdf` |
| ticketing | GET /tickets/TKT-56C43507/invoice | `ticketing/pdfs/TKT-56C43507_invoice.pdf` |
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
| files | GET /files/api/items/98/download | `files/leave_template_from_files.xlsx` |

## All checks

| Status | Module | Check | ms | Detail |
|--------|--------|-------|----|--------|
| PASS | shell | GET /health | 44 | HTTP 200 healthy |
| PASS | shell | PAGE / | 4 | HTTP 200 bytes=46341 |
| PASS | shell | PAGE /login | 3 | HTTP 200 bytes=17002 |
| PASS | shell | POST /api/auth/login | 372 | token present |
| PASS | shell | GET /api/auth/me | 3 | HTTP 200 |
| PASS | shell | PAGE /dashboard | 2 | HTTP 200 bytes=42792 |
| PASS | shell | PAGE /admin | 6 | HTTP 200 bytes=254716 |
| PASS | shell | PAGE /admin/dashboard | 3 | HTTP 200 bytes=254716 |
| PASS | shell | PAGE /dochub | 2 | HTTP 200 bytes=66924 |
| PASS | hr | PAGE /hr/ | 5 | HTTP 200 bytes=67068 |
| PASS | hr | PAGE /hr/my-requests | 3 | HTTP 200 bytes=45175 |
| PASS | hr | PAGE /hr/pending-review | 2 | HTTP 200 bytes=85830 |
| PASS | hr | PAGE /hr/approved-forms | 2 | HTTP 200 bytes=31723 |
| PASS | hr | PAGE /hr/hiring | 3 | HTTP 200 bytes=36810 |
| PASS | hr | PAGE /hr/leave-tracker | 4 | HTTP 200 bytes=53628 |
| PASS | hr | PAGE /hr/manpower-tracker | 8 | HTTP 200 bytes=42370 |
| PASS | hr | PAGE /hr/leave-application-form | 2 | HTTP 200 bytes=92215 |
| PASS | hr | PAGE /hr/commencement-form | 12 | HTTP 200 bytes=50951 |
| PASS | hr | PAGE /hr/duty-resumption-form | 14 | HTTP 200 bytes=72764 |
| PASS | hr | PAGE /hr/contract-renewal-form | 9 | HTTP 200 bytes=48038 |
| PASS | hr | PAGE /hr/performance-evaluation-form | 11 | HTTP 200 bytes=51548 |
| PASS | hr | PAGE /hr/grievance-form | 11 | HTTP 200 bytes=51430 |
| PASS | hr | PAGE /hr/interview-assessment-form | 8 | HTTP 200 bytes=42956 |
| PASS | hr | PAGE /hr/passport-release-form | 9 | HTTP 200 bytes=43816 |
| PASS | hr | PAGE /hr/staff-appraisal-form | 10 | HTTP 200 bytes=49740 |
| PASS | hr | PAGE /hr/station-clearance-form | 9 | HTTP 200 bytes=45171 |
| PASS | hr | PAGE /hr/visa-renewal-form | 8 | HTTP 200 bytes=40422 |
| PASS | hr | PAGE /hr/asset-handover-form | 11 | HTTP 200 bytes=56292 |
| PASS | hr | GET /hr/api/notifications/unread-count | 3 | HTTP 200 |
| PASS | hr | GET /hr/api/hiring/candidates | 13 | HTTP 200 |
| PASS | hr | GET /hr/api/leave-tracker/employees | 23 | HTTP 200 |
| PASS | hr | GET /hr/api/leave-tracker/export | 299 | HTTP 200 48075 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/leave-tracker/template | 36 | HTTP 200 11143 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/manpower/export | 103 | HTTP 200 22654 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/manpower/template | 43 | HTTP 200 16485 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/hiring/export | 94 | HTTP 200 12753 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/hiring/import-template | 49 | HTTP 200 9544 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | POST /hr/api/submit (leave) | 1520 | HTTP 200 |
| PASS | hr | GET /hr/api/my-submissions | 10 | HTTP 200 |
| PASS | hr | GET /hr/download-pdf/HR-LEAVE_APPLICATION-972F27E4 | 29 | HTTP 200 13143 bytes ctype=application/pdf |
| PASS | hr | builder PDF leave_application | 0 | 13934 bytes |
| PASS | hr | builder PDF commencement | 0 | 13409 bytes |
| PASS | hr | builder PDF duty_resumption | 0 | 12959 bytes |
| PASS | hr | builder PDF passport_release | 0 | 13707 bytes |
| PASS | hr | builder PDF grievance | 0 | 15595 bytes |
| PASS | hr | builder PDF visa_renewal | 0 | 13051 bytes |
| PASS | hr | builder PDF interview_assessment | 0 | 14934 bytes |
| PASS | hr | builder PDF staff_appraisal | 0 | 14065 bytes |
| PASS | hr | builder PDF station_clearance | 0 | 14313 bytes |
| PASS | hr | builder PDF performance_evaluation | 0 | 15600 bytes |
| PASS | hr | builder PDF contract_renewal | 0 | 16069 bytes |
| PASS | hr | builder PDF asset_handover | 0 | 12624 bytes |
| PASS | hr | HR PDF builders complete | 1396 | 12 PDFs |
| PASS | ticketing | PAGE /tickets/ | 10 | HTTP 200 bytes=51626 |
| PASS | ticketing | PAGE /tickets/list | 8 | HTTP 200 bytes=86034 |
| PASS | ticketing | PAGE /tickets/new | 6 | HTTP 200 bytes=205524 |
| PASS | ticketing | PAGE /tickets/drafts | 3 | HTTP 200 bytes=39339 |
| PASS | ticketing | PAGE /tickets/settings | 4 | HTTP 200 bytes=178897 |
| PASS | ticketing | GET /tickets/api/options | 60 | HTTP 200 |
| PASS | ticketing | GET /tickets/api/settings/projects | 9 | HTTP 200 |
| PASS | ticketing | GET /tickets/api/tickets/export | 42 | HTTP 200 8517 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | ticketing | GET /tickets/api/settings/locations/excel-template | 35 | HTTP 200 10182 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | ticketing | GET /tickets/api/settings/projects/8/locations/export | 28 | HTTP 200 10182 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | ticketing | POST /tickets/api/tickets (create) | 24 | HTTP 201 |
| PASS | ticketing | PAGE /tickets/TKT-56C43507 | 11 | HTTP 200 bytes=184574 |
| PASS | ticketing | GET /tickets/TKT-56C43507/pdf | 18 | HTTP 200 13304 bytes ctype=application/pdf |
| PASS | ticketing | GET /tickets/TKT-56C43507/invoice | 18 | HTTP 200 3670 bytes ctype=application/pdf |
| PASS | ticketing | POST triage-preview | 1587 | HTTP 200 |
| PASS | inspection | PAGE /inspection/ | 10 | HTTP 200 bytes=22814 |
| PASS | inspection | PAGE /inspection/form | 43 | HTTP 200 bytes=240553 |
| PASS | inspection | GET /inspection/dropdowns | 12 | HTTP 200 |
| PASS | inspection | builder hvac pdf | 0 | 16788 bytes |
| PASS | inspection | builder hvac xlsx | 0 | 164954 bytes |
| PASS | inspection | builder civil pdf | 0 | 13446 bytes |
| PASS | inspection | builder civil xlsx | 0 | 164567 bytes |
| PASS | inspection | builder cleaning pdf | 0 | 13460 bytes |
| PASS | inspection | builder cleaning xlsx | 0 | 164565 bytes |
| PASS | inspection | HVAC/Civil/Cleaning builders | 370 | 3 PDF + 3 Excel |
| PASS | qhsi | PAGE /qhsi/ | 14 | HTTP 200 bytes=27919 |
| PASS | qhsi | GET /qhsi/api/stats | 10 | HTTP 200 |
| PASS | qhsi | GET /qhsi/api/staff-compliance/import-template | 39 | HTTP 200 8408 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | qhsi | builder QHSI PDF | 21 | 19962 bytes |
| PASS | qhsi | builder QHSI Excel | 0 | 5217 bytes |
| PASS | mmr | PAGE /admin/mmr/ | 5 | HTTP 200 bytes=248305 |
| PASS | mmr | PAGE /admin/mmr-chargeable | 2 | HTTP 200 bytes=87315 |
| PASS | mmr | GET /admin/mmr/api/current-upload | 37 | HTTP 200 |
| PASS | mmr | GET /admin/mmr/api/automation-status | 3 | HTTP 200 |
| PASS | mmr | POST /admin/mmr/api/upload (cafm_sample.xlsx) | 22 | HTTP 200 {'dashboard': {'by_client': {'Ajman Municipality': 2}, 'by_contract': {'FM Contract A': 2}, 'by_priority': {'Hi |
| PASS | mmr | GET /admin/mmr/api/download-report | 96 | HTTP 200 117082 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | procurement | PAGE /procurement/ | 5 | HTTP 200 bytes=68854 |
| PASS | procurement | PAGE /procurement/materials | 4 | HTTP 200 bytes=50145 |
| PASS | procurement | GET /procurement/api/materials | 12 | HTTP 200 |
| PASS | procurement | GET /procurement/api/sample-excel | 30 | HTTP 200 8549 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | procurement | GET /procurement/api/export-excel | 24 | HTTP 200 7118 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | assets | PAGE /assets/ | 14 | HTTP 200 bytes=63669 |
| PASS | assets | PAGE /assets/executive | 9 | HTTP 200 bytes=32092 |
| PASS | assets | PAGE /assets/list | 4 | HTTP 200 bytes=32578 |
| PASS | assets | PAGE /assets/map | 4 | HTTP 200 bytes=33951 |
| PASS | assets | PAGE /assets/new | 20 | HTTP 200 bytes=46313 |
| PASS | assets | GET /assets/api/assets | 3 | HTTP 200 |
| PASS | assets | PAGE /assets/AST-0014 | 11 | HTTP 200 bytes=35591 |
| PASS | assets | GET /assets/api/assets/AST-0014 | 3 | HTTP 200 |
| PASS | assets | GET /assets/api/assets/AST-0014/qr-label.pdf | 12 | HTTP 200 6889 bytes ctype=application/pdf |
| PASS | assets | GET /assets/api/qr-labels.pdf | 125 | HTTP 200 72475 bytes ctype=application/pdf |
| PASS | assets | GET /assets/api/kpis | 5 | HTTP 200 |
| PASS | admin | PAGE /admin/devices | 2 | HTTP 200 bytes=93543 |
| PASS | admin | PAGE /admin/team-management | 2 | HTTP 200 bytes=153111 |
| PASS | admin | PAGE /admin/bd | 2 | HTTP 200 bytes=172456 |
| PASS | admin | PAGE /admin/knowledge-base | 2 | HTTP 200 bytes=50160 |
| PASS | admin | PAGE /admin/personal-progress | 1 | HTTP 200 bytes=42584 |
| PASS | admin | GET /api/admin/users | 10 | HTTP 200 |
| PASS | admin | GET /api/admin/devices/sample-excel | 27 | HTTP 200 8437 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | admin | GET /api/admin/technicians/export-template | 26 | HTTP 200 8334 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | files | PAGE /files/ | 16 | HTTP 200 bytes=28989 |
| PASS | files | POST save-from-module leave/template | 43 | HTTP 200 |
| PASS | files | GET /files/api/items/98/download | 3 | HTTP 200 11143 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | assistant | POST /api/assistant/chat | 804 | HTTP 200 |
