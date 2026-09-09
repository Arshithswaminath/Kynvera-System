# Module functional smoke — last run

- **When:** 2026-09-09T11:21:21
- **Target:** `https://operations.kynvera.net`
- **Artifacts:** `smoke_artifacts/20260909_112029`
- **Totals:** 126 passed, 1 failed, 0 warnings
- **Slow flags:** >5s candidate, >15s high

## Totals by module

| Module | Pass | Fail | Warn | Slow |
|--------|------|------|------|------|
| shell | 10 | 0 | 0 | 0 |
| hr | 45 | 0 | 0 | 0 |
| ticketing | 14 | 1 | 0 | 0 |
| inspection | 10 | 0 | 0 | 0 |
| qhsi | 5 | 0 | 0 | 0 |
| mmr | 6 | 0 | 0 | 0 |
| procurement | 5 | 0 | 0 | 0 |
| assets | 11 | 0 | 0 | 0 |
| admin | 8 | 0 | 0 | 0 |
| files | 3 | 0 | 0 | 0 |
| assistant | 1 | 0 | 0 | 0 |
| notifications | 7 | 0 | 0 | 0 |
| imports | 1 | 0 | 0 | 0 |

## Slow checks

None above the slow threshold.

## Failures

- **ticketing / POST triage-preview:** HTTP 502: {'error': "Messages.create() got an unexpected keyword argument 'temperature'", 'success': False, 'suggestion': None, 'triage_log_id': 5}

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
| hr | GET /hr/download-pdf/HR-LEAVE_APPLICATION-4D3AAD06 | `hr/pdfs/live_HR-LEAVE_APPLICATION-4D3AAD06.pdf` |
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
| ticketing | GET /tickets/TKT-7E31182F/pdf | `ticketing/pdfs/TKT-7E31182F_report.pdf` |
| ticketing | GET /tickets/TKT-7E31182F/invoice | `ticketing/pdfs/TKT-7E31182F_invoice.pdf` |
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
| PASS | shell | GET /health | 380 | HTTP 200 healthy |
| PASS | shell | PAGE / | 374 | HTTP 200 bytes=49819 |
| PASS | shell | PAGE /login | 458 | HTTP 200 bytes=20346 |
| PASS | shell | POST /api/auth/login (MFA) | 778 | TOTP accepted |
| PASS | shell | POST /api/auth/login | 778 | token present |
| PASS | shell | GET /api/auth/me | 338 | HTTP 200 |
| PASS | shell | PAGE /dashboard | 1177 | HTTP 200 bytes=42708 |
| PASS | shell | PAGE /admin | 745 | HTTP 200 bytes=266465 |
| PASS | shell | PAGE /admin/dashboard | 404 | HTTP 200 bytes=266465 |
| PASS | shell | PAGE /dochub | 406 | HTTP 200 bytes=67043 |
| PASS | hr | PAGE /hr/ | 338 | HTTP 200 bytes=68977 |
| PASS | hr | PAGE /hr/my-requests | 356 | HTTP 200 bytes=45139 |
| PASS | hr | PAGE /hr/pending-review | 389 | HTTP 200 bytes=85821 |
| PASS | hr | PAGE /hr/approved-forms | 354 | HTTP 200 bytes=31687 |
| PASS | hr | PAGE /hr/hiring | 387 | HTTP 200 bytes=41821 |
| PASS | hr | PAGE /hr/leave-tracker | 449 | HTTP 200 bytes=57948 |
| PASS | hr | PAGE /hr/employee-list | 384 | HTTP 200 bytes=42377 |
| PASS | hr | PAGE /hr/manpower-tracker | 355 | HTTP 200 bytes=50746 |
| PASS | hr | PAGE /hr/leave-application-form | 538 | HTTP 200 bytes=92179 |
| PASS | hr | PAGE /hr/commencement-form | 349 | HTTP 200 bytes=50915 |
| PASS | hr | PAGE /hr/duty-resumption-form | 372 | HTTP 200 bytes=72728 |
| PASS | hr | PAGE /hr/contract-renewal-form | 383 | HTTP 200 bytes=48002 |
| PASS | hr | PAGE /hr/performance-evaluation-form | 368 | HTTP 200 bytes=51512 |
| PASS | hr | PAGE /hr/grievance-form | 737 | HTTP 200 bytes=51394 |
| PASS | hr | PAGE /hr/interview-assessment-form | 386 | HTTP 200 bytes=42920 |
| PASS | hr | PAGE /hr/passport-release-form | 355 | HTTP 200 bytes=43780 |
| PASS | hr | PAGE /hr/staff-appraisal-form | 362 | HTTP 200 bytes=49704 |
| PASS | hr | PAGE /hr/station-clearance-form | 336 | HTTP 200 bytes=45135 |
| PASS | hr | PAGE /hr/visa-renewal-form | 341 | HTTP 200 bytes=40386 |
| PASS | hr | PAGE /hr/asset-handover-form | 357 | HTTP 200 bytes=56256 |
| PASS | hr | GET /hr/api/notifications/unread-count | 344 | HTTP 200 |
| PASS | hr | GET /hr/api/hiring/candidates | 424 | HTTP 200 |
| PASS | hr | GET /hr/api/leave-tracker/employees | 444 | HTTP 200 |
| PASS | hr | GET /hr/api/leave-tracker/export | 628 | HTTP 200 48274 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/leave-tracker/template | 381 | HTTP 200 11143 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/manpower/export | 527 | HTTP 200 27074 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/manpower/template | 402 | HTTP 200 16485 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/hiring/export | 869 | HTTP 200 12665 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | GET /hr/api/hiring/import-template | 374 | HTTP 200 9544 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | hr | POST /hr/api/submit (leave) | 2197 | HTTP 200 |
| PASS | hr | GET /hr/api/my-submissions | 364 | HTTP 200 |
| PASS | hr | GET /hr/download-pdf/HR-LEAVE_APPLICATION-4D3AAD06 | 405 | HTTP 200 13142 bytes ctype=application/pdf |
| PASS | hr | builder PDF leave_application | 0 | 13932 bytes |
| PASS | hr | builder PDF commencement | 0 | 13407 bytes |
| PASS | hr | builder PDF duty_resumption | 0 | 12960 bytes |
| PASS | hr | builder PDF passport_release | 0 | 13703 bytes |
| PASS | hr | builder PDF grievance | 0 | 15593 bytes |
| PASS | hr | builder PDF visa_renewal | 0 | 13051 bytes |
| PASS | hr | builder PDF interview_assessment | 0 | 14936 bytes |
| PASS | hr | builder PDF staff_appraisal | 0 | 14065 bytes |
| PASS | hr | builder PDF station_clearance | 0 | 14312 bytes |
| PASS | hr | builder PDF performance_evaluation | 0 | 15598 bytes |
| PASS | hr | builder PDF contract_renewal | 0 | 16067 bytes |
| PASS | hr | builder PDF asset_handover | 0 | 12623 bytes |
| PASS | hr | HR PDF builders complete | 768 | 12 PDFs |
| PASS | ticketing | PAGE /tickets/ | 437 | HTTP 200 bytes=51590 |
| PASS | ticketing | PAGE /tickets/list | 473 | HTTP 200 bytes=87562 |
| PASS | ticketing | PAGE /tickets/new | 421 | HTTP 200 bytes=205942 |
| PASS | ticketing | PAGE /tickets/drafts | 382 | HTTP 200 bytes=39303 |
| PASS | ticketing | PAGE /tickets/settings | 475 | HTTP 200 bytes=178946 |
| PASS | ticketing | GET /tickets/api/options | 799 | HTTP 200 |
| PASS | ticketing | GET /tickets/api/settings/projects | 350 | HTTP 200 |
| PASS | ticketing | GET /tickets/api/tickets/export | 382 | HTTP 200 8591 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | ticketing | GET /tickets/api/settings/locations/excel-template | 367 | HTTP 200 10182 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | ticketing | GET /tickets/api/settings/projects/8/locations/export | 370 | HTTP 200 10182 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | ticketing | POST /tickets/api/tickets (create) | 364 | HTTP 201 |
| PASS | ticketing | PAGE /tickets/TKT-7E31182F | 582 | HTTP 200 bytes=184538 |
| PASS | ticketing | GET /tickets/TKT-7E31182F/pdf | 366 | HTTP 200 13304 bytes ctype=application/pdf |
| PASS | ticketing | GET /tickets/TKT-7E31182F/invoice | 353 | HTTP 200 3672 bytes ctype=application/pdf |
| FAIL | ticketing | POST triage-preview | 2886 | HTTP 502: {'error': "Messages.create() got an unexpected keyword argument 'temperature'", 'success': False, 'suggestion' |
| PASS | inspection | PAGE /inspection/ | 406 | HTTP 200 bytes=22705 |
| PASS | inspection | PAGE /inspection/form | 576 | HTTP 200 bytes=240521 |
| PASS | inspection | GET /inspection/dropdowns | 311 | HTTP 200 |
| PASS | inspection | builder hvac pdf | 0 | 16784 bytes |
| PASS | inspection | builder hvac xlsx | 0 | 133400 bytes |
| PASS | inspection | builder civil pdf | 0 | 13448 bytes |
| PASS | inspection | builder civil xlsx | 0 | 133016 bytes |
| PASS | inspection | builder cleaning pdf | 0 | 13461 bytes |
| PASS | inspection | builder cleaning xlsx | 0 | 133015 bytes |
| PASS | inspection | HVAC/Civil/Cleaning builders | 116 | 3 PDF + 3 Excel |
| PASS | qhsi | PAGE /qhsi/ | 469 | HTTP 200 bytes=27810 |
| PASS | qhsi | GET /qhsi/api/stats | 369 | HTTP 200 |
| PASS | qhsi | GET /qhsi/api/staff-compliance/import-template | 368 | HTTP 200 8405 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | qhsi | builder QHSI PDF | 19 | 19962 bytes |
| PASS | qhsi | builder QHSI Excel | 0 | 5215 bytes |
| PASS | mmr | PAGE /admin/mmr/ | 428 | HTTP 200 bytes=250394 |
| PASS | mmr | PAGE /admin/mmr-chargeable | 344 | HTTP 200 bytes=94761 |
| PASS | mmr | GET /admin/mmr/api/current-upload | 314 | HTTP 200 |
| PASS | mmr | GET /admin/mmr/api/automation-status | 345 | HTTP 200 |
| PASS | mmr | POST /admin/mmr/api/upload (cafm_sample.xlsx) | 1608 | HTTP 200 {'dashboard': {'by_client': {'Ajman Municipality': 2}, 'by_contract': {'FM Contract A': 2}, 'by_priority': {'Hi |
| PASS | mmr | GET /admin/mmr/api/download-report | 517 | HTTP 200 54277 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | procurement | PAGE /procurement/ | 368 | HTTP 200 bytes=68818 |
| PASS | procurement | PAGE /procurement/materials | 392 | HTTP 200 bytes=50109 |
| PASS | procurement | GET /procurement/api/materials | 348 | HTTP 200 |
| PASS | procurement | GET /procurement/api/sample-excel | 389 | HTTP 200 8548 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | procurement | GET /procurement/api/export-excel | 359 | HTTP 200 7117 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | assets | PAGE /assets/ | 411 | HTTP 200 bytes=63826 |
| PASS | assets | PAGE /assets/executive | 364 | HTTP 200 bytes=32251 |
| PASS | assets | PAGE /assets/list | 336 | HTTP 200 bytes=32756 |
| PASS | assets | PAGE /assets/map | 327 | HTTP 200 bytes=34110 |
| PASS | assets | PAGE /assets/new | 519 | HTTP 200 bytes=46472 |
| PASS | assets | GET /assets/api/assets | 320 | HTTP 200 |
| PASS | assets | PAGE /assets/AST-0014 | 484 | HTTP 200 bytes=36158 |
| PASS | assets | GET /assets/api/assets/AST-0014 | 321 | HTTP 200 |
| PASS | assets | GET /assets/api/assets/AST-0014/qr-label.pdf | 343 | HTTP 200 8269 bytes ctype=application/pdf |
| PASS | assets | GET /assets/api/qr-labels.pdf | 656 | HTTP 200 92388 bytes ctype=application/pdf |
| PASS | assets | GET /assets/api/kpis | 333 | HTTP 200 |
| PASS | admin | PAGE /admin/devices | 399 | HTTP 200 bytes=94121 |
| PASS | admin | PAGE /admin/team-management | 407 | HTTP 200 bytes=154616 |
| PASS | admin | PAGE /admin/bd | 399 | HTTP 200 bytes=183655 |
| PASS | admin | PAGE /admin/knowledge-base | 336 | HTTP 200 bytes=50124 |
| PASS | admin | PAGE /admin/personal-progress | 372 | HTTP 200 bytes=42548 |
| PASS | admin | GET /api/admin/users | 557 | HTTP 200 |
| PASS | admin | GET /api/admin/devices/sample-excel | 352 | HTTP 200 8437 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | admin | GET /api/admin/technicians/export-template | 444 | HTTP 200 8334 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | files | PAGE /files/ | 598 | HTTP 200 bytes=29095 |
| PASS | files | POST save-from-module leave/template | 956 | HTTP 200 |
| PASS | files | GET /files/api/items/99/download | 402 | HTTP 200 11142 bytes ctype=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| PASS | assistant | POST /api/assistant/chat | 337 | HTTP 200 |
| PASS | notifications | GET /hr/api/notifications | 333 | HTTP 200 |
| PASS | notifications | GET /hr/api/notifications/unread-count | 311 | HTTP 200 |
| PASS | notifications | PAGE /admin/email-notifications | 788 | HTTP 200 bytes=266465 |
| PASS | notifications | GET /api/admin/email-logs | 330 | HTTP 200 |
| PASS | notifications | GET /api/admin/notification-config | 313 | HTTP 200 |
| PASS | notifications | GET /api/admin/users | 400 | HTTP 200 |
| PASS | notifications | GET edit-otp/status (no send) | 351 | HTTP 200 |
| PASS | imports | Excel import POSTs | 0 | skipped on live — would mutate production data |
