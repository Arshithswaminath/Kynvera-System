# Complete Test Plan - Short Time Owner Feature

## Summary of Changes

### Backend Changes (All 3 Modules: Cleaning, Civil, HVAC/MEP)
1. **Permission Logic (`routes.py`)**:
   - OM can edit at `operations_manager_review` OR `bd_procurement_review` (if BD/Procurement haven't started)
   - BD can edit at `bd_procurement_review` OR `general_manager_review` (if GM hasn't approved)
   - Procurement can edit at `bd_procurement_review` OR `general_manager_review` (if GM hasn't approved)
   - GM can edit at `general_manager_review` OR `completed`
   - Added `can_edit` flag to `submission_data` dictionary

2. **Workflow Approval Endpoints (`app/workflow/routes.py`)**:
   - OM approval: allows re-approval when status is `operations_manager_review` OR `bd_procurement_review`
   - BD approval: allows re-approval when status is `bd_procurement_review` OR `general_manager_review`
   - Procurement approval: allows re-approval when status is `bd_procurement_review` OR `general_manager_review`
   - GM approval: allows re-approval when status is `general_manager_review` OR `completed`

### Frontend Changes (All 3 Templates)
1. **OM Section**: Added can_edit check to show editable vs read-only sections
2. **BD Section**: Added can_edit check before disabling signature pads
3. **Procurement Section**: Added can_edit check before disabling signature pads
4. **GM Section**: Added can_edit check before disabling signature pads
5. **Timezone Fix**: Added `formatSigningTime` function to convert UTC to Dubai time (GST)
6. **Signature Loading**: Fixed CORS issues using `ctx.drawImage()` instead of `fromDataURL()`
7. **Signature Hints**: Show "(You can edit and re-sign if needed)" only to the current owner
8. **Read-Only Sections**: Added sections for each role to view previous reviewers' signatures

---

## Test Scenarios

### 1. Supervisor Flow
| Step | Action | Expected Result |
|------|--------|----------------|
| 1.1 | Supervisor submits form | ✓ Form moves to `operations_manager_review` |
| 1.2 | Supervisor views their form | ✓ Signature shows "✓ Form signed (You can edit and re-sign if needed)" |
| 1.3 | Supervisor can clear and re-sign | ✓ Clear button works, can draw new signature |
| 1.4 | OM signs the form | ✓ Form moves to `bd_procurement_review` |
| 1.5 | Supervisor views after OM signs | ✓ Signature shows "✓ Form signed" (no edit option) |
| 1.6 | Supervisor sees OM's signature | ✓ OM signature/comments visible in "Previous Reviews" section |

### 2. Operations Manager Flow
| Step | Action | Expected Result |
|------|--------|----------------|
| 2.1 | OM reviews form | ✓ Can see Supervisor signature in read-only section above |
| 2.2 | OM signs form | ✓ Form moves to `bd_procurement_review` |
| 2.3 | OM views their signed form | ✓ Shows "✓ Signed: [GST time] (You can edit and re-sign if needed)" |
| 2.4 | OM can clear and re-sign | ✓ Clear button works before BD/Procurement approve |
| 2.5 | BD signs (or Procurement signs) | ✓ OM can no longer edit |
| 2.6 | OM views after BD/Proc signs | ✓ Shows "✓ Form signed" (no edit option) |
| 2.7 | OM sees all reviewers' signatures | ✓ Supervisor, BD, Procurement visible in "Previous Reviews" |

### 3. Business Development Flow
| Step | Action | Expected Result |
|------|--------|----------------|
| 3.1 | BD reviews form | ✓ Can see Supervisor + OM signatures in read-only sections |
| 3.2 | BD signs form | ✓ Stays at `bd_procurement_review` (waiting for Procurement) |
| 3.3 | BD views their signed form | ✓ Shows "✓ Signed: [GST time] (You can edit and re-sign if needed)" |
| 3.4 | BD can clear and re-sign | ✓ Clear button works, signature pad enabled |
| 3.5 | Procurement also signs | ✓ Form moves to `general_manager_review` |
| 3.6 | BD still views form | ✓ Still shows "(You can edit and re-sign if needed)" until GM signs |
| 3.7 | GM signs | ✓ BD can no longer edit |
| 3.8 | BD views after GM signs | ✓ Shows "✓ Form signed" (read-only, no edit option) |

### 4. Procurement Flow
| Step | Action | Expected Result |
|------|--------|----------------|
| 4.1 | Procurement reviews form | ✓ Can see Supervisor + OM + BD signatures in read-only sections |
| 4.2 | Procurement signs form | ✓ Stays at `bd_procurement_review` if BD hasn't signed yet |
| 4.3 | Procurement views signed form | ✓ Shows "✓ Signed: [GST time] (You can edit and re-sign if needed)" |
| 4.4 | Procurement can re-sign | ✓ Clear button works, signature pad enabled |
| 4.5 | BD also signs | ✓ Form moves to `general_manager_review` |
| 4.6 | Procurement still edits | ✓ Still shows "(You can edit and re-sign if needed)" until GM signs |
| 4.7 | GM signs | ✓ Procurement can no longer edit |
| 4.8 | Procurement views after GM | ✓ Shows "✓ Form signed" (read-only) |

### 5. General Manager Flow
| Step | Action | Expected Result |
|------|--------|----------------|
| 5.1 | GM reviews form | ✓ Can see all previous signatures (Supervisor, OM, BD, Procurement) |
| 5.2 | GM signs form | ✓ Form status changes to `completed` |
| 5.3 | GM views completed form | ✓ Shows "✓ Signed: [GST time] (You can edit and re-sign if needed)" |
| 5.4 | GM can re-sign even after completion | ✓ Clear button works, signature pad enabled |
| 5.5 | Other users view completed form | ✓ All users see all signatures in read-only mode |

### 6. Signature Display Tests
| Scenario | Expected Result |
|----------|----------------|
| Signature stored as data URL | ✓ Displays correctly |
| Signature stored as HTTP URL | ✓ Displays correctly (uses `ctx.drawImage`) |
| Signature stored as object with .url property | ✓ Extracts URL and displays correctly |
| Canvas resize | ✓ Signature doesn't clear (protected by `dataset.signatureLoaded`) |

### 7. Timezone Tests
| Input Timestamp | Expected Display Format |
|-----------------|------------------------|
| `2026-01-25T11:53:25.269729` | `Jan 25, 03:53 PM (GST)` |
| `2026-01-25T11:53:25Z` | `Jan 25, 03:53 PM (GST)` |
| `2026-01-25T11:53:25+04:00` | `Jan 25, 11:53 AM (GST)` |

### 8. Edge Cases to Test
| Scenario | Expected Behavior |
|----------|------------------|
| OM re-signs after initially signing | ✓ Updates timestamp, saves new signature |
| BD signs, then Procurement signs, BD tries to re-sign | ✓ BD can still re-sign until GM approves |
| GM completes form, then edits their review | ✓ GM can edit even after completion |
| Supervisor views form after 3 stages | ✓ Read-only, sees all signatures below |
| Admin views any form | ✓ Can see all signatures, proper edit permissions based on role |

### 9. Negative Test Cases
| Scenario | Expected Result |
|----------|----------------|
| Supervisor tries to edit after OM signs | ✗ Form is read-only, "Previous Reviews" shown |
| OM tries to edit after BD+Procurement sign | ✗ Form is read-only |
| BD tries to edit after GM signs | ✗ Form is read-only |
| Non-owner tries to access form | ✗ Access denied or read-only |

---

## Testing Checklist

### Module Testing
- [ ] Cleaning Module - All scenarios
- [ ] Civil Module - All scenarios
- [ ] HVAC/MEP Module - All scenarios

### Cross-Browser Testing
- [ ] Chrome/Edge
- [ ] Firefox
- [ ] Safari (if applicable)
- [ ] Mobile browsers

### Data Integrity
- [ ] Check database after each signature to ensure data persistence
- [ ] Verify PDFs contain all signatures
- [ ] Verify Excel reports contain all data
- [ ] Check that re-signing updates the timestamp correctly

### UI/UX
- [ ] Signature hints show correct messages
- [ ] Clear buttons appear/disappear correctly
- [ ] Signature pads enable/disable correctly
- [ ] Read-only sections display properly
- [ ] Timestamps show in GST format

---

## Known Issues Fixed

1. ✅ OM locked out after signing
2. ✅ BD/Procurement locked out after signing
3. ✅ GM locked out after signing
4. ✅ Signatures not displaying (CORS issue)
5. ✅ Wrong timezone (UTC instead of GST)
6. ✅ Canvas clearing on resize
7. ✅ BD/Procurement/GM signature pads disabled even when can edit
8. ✅ Supervisor signature hint not updating after submission
9. ✅ BD signatures not showing for OM viewing
10. ✅ "(You can edit and re-sign)" showing to wrong users

---

## Additional Notes

- All forms now use the **Cleaning form approach** as the standard
- Backend `can_edit` flag is the single source of truth
- Frontend respects backend permissions
- All signatures use Dubai timezone (GST)
- Signature loading uses `ctx.drawImage()` for reliability
