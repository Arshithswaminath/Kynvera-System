# Module functional smoke — last run

- **When:** 2026-08-21T13:58:55
- **Target:** `https://operations.kynvera.net`
- **Artifacts:** `smoke_artifacts/20260821_135721`
- **Totals:** 114 passed, 0 failed, 3 warnings
- **Slow flags:** >5s candidate, >15s high

## Totals by module

| Module | Pass | Fail | Warn | Slow |
|--------|------|------|------|------|
| shell | 9 | 0 | 0 | 0 |
| hr | 44 | 0 | 0 | 0 |
| ticketing | 12 | 0 | 3 | 1 |
| inspection | 10 | 0 | 0 | 0 |
| qhsi | 5 | 0 | 0 | 0 |
| mmr | 6 | 0 | 0 | 2 |
| procurement | 5 | 0 | 0 | 0 |
| assets | 11 | 0 | 0 | 0 |
| admin | 8 | 0 | 0 | 0 |
| files | 3 | 0 | 0 | 0 |
| assistant | 1 | 0 | 0 | 0 |

## Slow checks

| Status | Module | Check | ms |
|--------|--------|-------|----|
| PASS | ticketing | POST triage-preview | 12166 |
| PASS | mmr | POST /admin/mmr/api/upload (RM Deatils MMR (4).xlsx) | 8360 |
| PASS | mmr | GET /admin/mmr/api/download-report | 5798 |

## Failures

None.

## Warnings

- **ticketing / GET /tickets/api/tickets/export:** HTTP 404 ctype=text/html head=b'<!doctype ht'
- **ticketing / GET /tickets/api/settings/locations/excel-template:** HTTP 404 ctype=text/html head=b'<!doctype ht'
- **ticketing / GET /tickets/api/settings/projects/2/locations/export:** HTTP 404 ctype=text/html head=b'<!doctype ht'

## Saved artifacts

| Module | Check | File |
|--------|-------|------|
| hr | GET /hr/api/leave-tracker/export | `hr/xlsx/leave_tracker_export.xlsx` |
| hr | GET /hr/api/leave-tracker/template | `hr/xlsx/leave_log_template.xlsx` |
| hr | GET /hr/api/manpower/export | `hr/xlsx/manpower_export.xlsx` |
| hr | GET /hr/api/manpower/template | `hr/xlsx/manpower_template.xlsx` |
| hr | GET /hr/api/hiring/export | `hr/xlsx/hiring_export.xlsx` |
| hr | GET /hr/api/hiring/import-template | `hr/xlsx/hiring_import_template.xlsx` |
| hr | GET /hr/download-pdf/HR-LEAVE_APPLICATION-424F79B1 | `hr/pdfs/live_HR-LEAVE_APPLICATION-424F79B1.pdf` |
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
| ticketing | GET /tickets/TKT-649A28A5/pdf | `ticketing/pdfs/TKT-649A28A5_report.pdf` |
| ticketing | GET /tickets/TKT-649A28A5/invoice | `ticketing/pdfs/TKT-649A28A5_invoice.pdf` |
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
| assets | GET /assets/api/assets/AST-0002/qr-label.pdf | `assets/pdfs/AST-0002-qr-label.pdf` |
| assets | GET /assets/api/qr-labels.pdf | `assets/pdfs/asset-qr-labels.pdf` |
| admin | GET /api/admin/devices/sample-excel | `admin/xlsx/devices_sample.xlsx` |
| admin | GET /api/admin/technicians/export-template | `admin/xlsx/technicians_template.xlsx` |
| files | GET /files/api/items/2/download | `files/leave_template_from_files.xlsx` |

## All checks

| Status | Module | Check | ms | Detail |
|--------|--------|-------|----|--------|
| PASS | shell | GET /health | 389 | HTTP 200 healthy |
| PASS | shell | PAGE / | 370 | HTTP 200 bytes=46894 |
| PASS | shell | PAGE /login | 1758 | HTTP 200 bytes=12958 |
| PASS | shell | POST /api/auth/login | 2271 | token present |
| PASS | shell | GET /api/auth/me | 356 | HTTP 200 |
| PASS | shell | PAGE /dashboard | 450 | HTTP 200 bytes=41949 |
| PASS | shell | PAGE /admin | 1214 | HTTP 200 bytes=237763 |
| PASS | shell | PAGE /admin/dashboard | 732 | HTTP 200 bytes=237763 |
| PASS | shell | PAGE /dochub | 790 | HTTP 200 bytes=65898 |
| PASS | hr | PAGE /hr/ | 2747 | HTTP 200 bytes=61487 |
| PASS | hr | PAGE /hr/my-requests | 407 | HTTP 200 bytes=43631 |
| PASS | hr | PAGE /hr/pending-review | 658 | HTTP 200 bytes=87418 |
| PASS | hr | PAGE /hr/approved-forms | 1403 | HTTP 200 bytes=30924 |
| PASS | hr | PAGE /hr/hiring | 710 | HTTP 200 bytes=32251 |
| PASS | hr | PAGE /hr/leave-tracker | 544 | HTTP 200 bytes=45020 |
| PASS | hr | PAGE /hr/manpower-tracker | 486 | HTTP 200 bytes=39263 |
| PASS | hr | PAGE /hr/leave-application-form | 623 | HTTP 200 bytes=89228 |
| PASS | hr | PAGE /hr/commencement-form | 1181 | HTTP 200 bytes=49466 |
| PASS | hr | PAGE /hr/duty-resumption-form | 465 | HTTP 200 bytes=72729 |
| PASS | hr | PAGE /hr/contract-renewal-form | 523 | HTTP 200 bytes=46538 |
| PASS | hr | PAGE /hr/performance-evaluation-form | 534 | HTTP 200 bytes=50048 |
| PASS | hr | PAGE /hr/grievance-form | 735 | HTTP 200 bytes=49928 |
| PASS | hr | PAGE /hr/interview-assessment-form | 3643 | HTTP 200 bytes=41384 |
| PASS | hr | PAGE /hr/passport-release-form | 369 | HTTP 200 bytes=42301 |
| PASS | hr | PAGE /hr/staff-appraisal-form | 356 | HTTP 200 bytes=48240 |
| PASS | hr | PAGE /hr/station-clearance-form | 366 | HTTP 200 bytes=43656 |
| PASS | hr | PAGE /hr/visa-renewal-form | 422 | HTTP 200 bytes=38909 |
| PASS | hr | PAGE /hr/asset-handover-form | 370 | HTTP 200 bytes=54790 |
| PASS | hr | GET /hr/api/notifications/unread-count | 437 | HTTP 200 |
| PASS | hr | GET /hr/api/hiring/candidates | 511 | HTTP 200 |
| PASS | hr | GET /hr/api/leave-tracker/employees | 604 | HTTP 200 |
| PASS | hr | GET /hr/api/leave-tracker/export | 3066 | HTTP 200 45103 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/leave-tracker/template | 391 | HTTP 200 9241 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/manpower/export | 796 | HTTP 200 8723 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/manpower/template | 404 | HTTP 200 6371 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/hiring/export | 788 | HTTP 200 10069 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/hiring/import-template | 815 | HTTP 200 7616 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | POST /hr/api/submit (leave) | 431 | HTTP 200 |
| PASS | hr | GET /hr/api/my-submissions | 370 | HTTP 200 |
| PASS | hr | GET /hr/download-pdf/HR-LEAVE_APPLICATION-424F79B1 | 591 | HTTP 200 13049 bytes ctype=application/pdf |
| PASS | hr | builder PDF leave_application | 0 | 13934 bytes |
| PASS | hr | builder PDF commencement | 0 | 13416 bytes |
| PASS | hr | builder PDF duty_resumption | 0 | 12966 bytes |
| PASS | hr | builder PDF passport_release | 0 | 13707 bytes |
| PASS | hr | builder PDF grievance | 0 | 15597 bytes |
| PASS | hr | builder PDF visa_renewal | 0 | 13061 bytes |
| PASS | hr | builder PDF interview_assessment | 0 | 14934 bytes |
| PASS | hr | builder PDF staff_appraisal | 0 | 14066 bytes |
| PASS | hr | builder PDF station_clearance | 0 | 14313 bytes |
| PASS | hr | builder PDF performance_evaluation | 0 | 15600 bytes |
| PASS | hr | builder PDF contract_renewal | 0 | 16072 bytes |
| PASS | hr | builder PDF asset_handover | 0 | 12624 bytes |
| PASS | hr | HR PDF builders complete | 1194 | 12 PDFs |
| PASS | ticketing | PAGE /tickets/ | 1002 | HTTP 200 bytes=44772 |
| PASS | ticketing | PAGE /tickets/list | 411 | HTTP 200 bytes=35061 |
| PASS | ticketing | PAGE /tickets/new | 726 | HTTP 200 bytes=201035 |
| PASS | ticketing | PAGE /tickets/drafts | 414 | HTTP 200 bytes=32237 |
| PASS | ticketing | PAGE /tickets/settings | 498 | HTTP 200 bytes=110927 |
| PASS | ticketing | GET /tickets/api/options | 766 | HTTP 200 |
| PASS | ticketing | GET /tickets/api/settings/projects | 390 | HTTP 200 |
| WARN | ticketing | GET /tickets/api/tickets/export | 706 | HTTP 404 ctype=text/html head=b'<!doctype ht' |
| WARN | ticketing | GET /tickets/api/settings/locations/excel-template | 433 | HTTP 404 ctype=text/html head=b'<!doctype ht' |
| WARN | ticketing | GET /tickets/api/settings/projects/2/locations/export | 374 | HTTP 404 ctype=text/html head=b'<!doctype ht' |
| PASS | ticketing | POST /tickets/api/tickets (create) | 378 | HTTP 201 |
| PASS | ticketing | PAGE /tickets/TKT-649A28A5 | 1779 | HTTP 200 bytes=171859 |
| PASS | ticketing | GET /tickets/TKT-649A28A5/pdf | 516 | HTTP 200 13326 bytes ctype=application/pdf |
| PASS | ticketing | GET /tickets/TKT-649A28A5/invoice | 645 | HTTP 200 3681 bytes ctype=application/pdf |
| PASS | ticketing | POST triage-preview | 12166 | HTTP 200 |
| PASS | inspection | PAGE /inspection/ | 375 | HTTP 200 bytes=21328 |
| PASS | inspection | PAGE /inspection/form | 1696 | HTTP 200 bytes=238738 |
| PASS | inspection | GET /inspection/dropdowns | 396 | HTTP 200 |
| PASS | inspection | builder hvac pdf | 0 | 17513 bytes |
| PASS | inspection | builder hvac xlsx | 0 | 164971 bytes |
| PASS | inspection | builder civil pdf | 0 | 13781 bytes |
| PASS | inspection | builder civil xlsx | 0 | 164584 bytes |
| PASS | inspection | builder cleaning pdf | 0 | 13775 bytes |
| PASS | inspection | builder cleaning xlsx | 0 | 164582 bytes |
| PASS | inspection | HVAC/Civil/Cleaning builders | 240 | 3 PDF + 3 Excel |
| PASS | qhsi | PAGE /qhsi/ | 955 | HTTP 200 bytes=27266 |
| PASS | qhsi | GET /qhsi/api/stats | 405 | HTTP 200 |
| PASS | qhsi | GET /qhsi/api/staff-compliance/import-template | 360 | HTTP 200 6077 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | qhsi | builder QHSI PDF | 33 | 19987 bytes |
| PASS | qhsi | builder QHSI Excel | 0 | 5217 bytes |
| PASS | mmr | PAGE /admin/mmr/ | 789 | HTTP 200 bytes=247290 |
| PASS | mmr | PAGE /admin/mmr-chargeable | 455 | HTTP 200 bytes=86294 |
| PASS | mmr | GET /admin/mmr/api/current-upload | 434 | HTTP 200 |
| PASS | mmr | GET /admin/mmr/api/automation-status | 355 | HTTP 200 |
| PASS | mmr | POST /admin/mmr/api/upload (RM Deatils MMR (4).xlsx) | 8360 | HTTP 200 {'dashboard': {'by_client': {'Aqaar Community Mangement': 17, 'Askaan Properties LLC': 29, 'Saqr Real Estate':  |
| PASS | mmr | GET /admin/mmr/api/download-report | 5798 | HTTP 200 193987 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | procurement | PAGE /procurement/ | 524 | HTTP 200 bytes=51264 |
| PASS | procurement | PAGE /procurement/materials | 661 | HTTP 200 bytes=17229 |
| PASS | procurement | GET /procurement/api/materials | 980 | HTTP 200 |
| PASS | procurement | GET /procurement/api/sample-excel | 468 | HTTP 200 5486 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | procurement | GET /procurement/api/export-excel | 360 | HTTP 200 4791 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | assets | PAGE /assets/ | 642 | HTTP 200 bytes=34023 |
| PASS | assets | PAGE /assets/executive | 592 | HTTP 200 bytes=30131 |
| PASS | assets | PAGE /assets/list | 612 | HTTP 200 bytes=29443 |
| PASS | assets | PAGE /assets/map | 744 | HTTP 200 bytes=28495 |
| PASS | assets | PAGE /assets/new | 542 | HTTP 200 bytes=29563 |
| PASS | assets | GET /assets/api/assets | 338 | HTTP 200 |
| PASS | assets | PAGE /assets/AST-0002 | 753 | HTTP 200 bytes=33373 |
| PASS | assets | GET /assets/api/assets/AST-0002 | 381 | HTTP 200 |
| PASS | assets | GET /assets/api/assets/AST-0002/qr-label.pdf | 428 | HTTP 200 8214 bytes ctype=application/pdf |
| PASS | assets | GET /assets/api/qr-labels.pdf | 1789 | HTTP 200 85725 bytes ctype=application/pdf |
| PASS | assets | GET /assets/api/kpis | 453 | HTTP 200 |
| PASS | admin | PAGE /admin/devices | 524 | HTTP 200 bytes=96043 |
| PASS | admin | PAGE /admin/team-management | 453 | HTTP 200 bytes=119363 |
| PASS | admin | PAGE /admin/bd | 606 | HTTP 200 bytes=76685 |
| PASS | admin | PAGE /admin/knowledge-base | 419 | HTTP 200 bytes=49165 |
| PASS | admin | PAGE /admin/personal-progress | 438 | HTTP 200 bytes=41036 |
| PASS | admin | GET /api/admin/users | 506 | HTTP 200 |
| PASS | admin | GET /api/admin/devices/sample-excel | 391 | HTTP 200 5494 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | admin | GET /api/admin/technicians/export-template | 516 | HTTP 200 6542 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | files | PAGE /files/ | 590 | HTTP 200 bytes=23247 |
| PASS | files | POST save-from-module leave/template | 490 | HTTP 200 |
| PASS | files | GET /files/api/items/2/download | 374 | HTTP 200 9240 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | assistant | POST /api/assistant/chat | 1071 | HTTP 200 |
