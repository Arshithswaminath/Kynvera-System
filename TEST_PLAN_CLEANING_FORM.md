# Cleaning Form Test Plan
## Multi-Stage Approval Workflow with Read-Only Access

### Prerequisites
1. Start the Flask server: `python run.py` or `flask run`
2. Have test accounts for each role:
   - Supervisor account
   - Operations Manager account
   - Business Development account
   - Procurement account
   - General Manager account

---

## Test Case 1: Supervisor Submits New Form

### Steps:
1. **Login** as Supervisor
2. Navigate to **Cleaning Services** module
3. Fill in the form:
   - Project Name: "Test Project - TC1"
   - Date of Visit: Today's date
   - Fill in facility counts (any values)
   - Go to Tab 4 (Visual Evidence) - add a photo (optional)
   - Go to Tab 5 (Sign-off & Submit)
4. Add **Supervisor Comments**: "Initial supervisor comments"
5. **Sign** in the signature pad
6. Click **Verified** button
7. Click **Submit & Generate Reports**

### Expected Results:
- [ ] Form submits successfully
- [ ] Download links appear (PDF & Excel)
- [ ] Supervisor can see their own signature and comments
- [ ] Signature hint shows "✓ Form signed"

---

## Test Case 2: Operations Manager Reviews Form

### Steps:
1. **Login** as Operations Manager
2. Navigate to **Dashboard** → **Pending Approvals**
3. Find the form submitted by Supervisor (Test Project - TC1)
4. Click to open/review the form

### Expected Results:
- [ ] Form opens in edit mode (can edit OM section)
- [ ] "Previous Reviews" section shows **Supervisor's review**:
  - Supervisor comments visible
  - Supervisor signature visible
  - Timestamp displayed
- [ ] OM has their own editable section:
  - Comments textarea
  - Signature pad
5. Add **OM Comments**: "Operations Manager review complete"
6. **Sign** in OM signature pad
7. Click **Update Submission**

### Expected Results:
- [ ] Form submits successfully
- [ ] Page reloads showing OM's signature
- [ ] Shows "✓ Form signed" indicator

---

## Test Case 3: Supervisor Views Form After OM Approval (READ-ONLY)

### Steps:
1. **Login** as Supervisor (same account from TC1)
2. Navigate to **Dashboard** → **Review History**
3. Find the form "Test Project - TC1"
4. Click to open/review

### Expected Results:
- [ ] **Blue "Read-Only Mode" banner** appears at top
- [ ] "Previous Reviews" section shows **OM's review**:
  - OM comments visible
  - OM signature visible
  - Timestamp displayed
- [ ] Supervisor's own signature is visible (read-only)
- [ ] **NO submit button** - shows "Read-Only: This form is view-only"
- [ ] All form fields are visible but supervisor cannot edit

---

## Test Case 4: Business Development Reviews Form

### Steps:
1. **Login** as Business Development
2. Navigate to **Dashboard** → **Pending Approvals**
3. Find the form "Test Project - TC1"
4. Click to open/review

### Expected Results:
- [ ] Form opens in edit mode (can edit BD section)
- [ ] "Previous Reviews" section shows:
  - Supervisor's comments + signature
  - OM's comments + signature
- [ ] BD has their own editable section
5. Add **BD Comments**: "BD approval granted"
6. **Sign** in BD signature pad
7. Click **Update Submission**

### Expected Results:
- [ ] Form submits successfully
- [ ] BD signature appears in review

---

## Test Case 5: OM Views Form After BD Approval (READ-ONLY)

### Steps:
1. **Login** as Operations Manager
2. Navigate to **Dashboard** → **Review History**
3. Find the form "Test Project - TC1"

### Expected Results:
- [ ] **Blue "Read-Only Mode" banner** appears
- [ ] Previous Reviews shows: Supervisor, BD, Procurement (if signed)
- [ ] OM's own previous review is visible
- [ ] **NO submit button**
- [ ] OM cannot edit anymore

---

## Test Case 6: Procurement Reviews Form

### Steps:
1. **Login** as Procurement
2. Navigate to **Dashboard** → **Pending Approvals**
3. Find the form "Test Project - TC1"
4. Click to open/review

### Expected Results:
- [ ] Form opens in edit mode (can edit Procurement section)
- [ ] Previous Reviews shows: Supervisor, OM, BD
5. Add **Procurement Comments**: "Procurement review done"
6. **Sign** in Procurement signature pad
7. Click **Update Submission**

### Expected Results:
- [ ] Form submits successfully

---

## Test Case 7: General Manager Final Approval

### Steps:
1. **Login** as General Manager
2. Navigate to **Dashboard** → **Pending Approvals**
3. Find the form "Test Project - TC1"
4. Click to open/review

### Expected Results:
- [ ] Form opens in edit mode (can edit GM section)
- [ ] Previous Reviews shows: Supervisor, OM, BD, Procurement
5. Add **GM Comments**: "Approved by GM"
6. **Sign** in GM signature pad
7. Click **Update Submission**

### Expected Results:
- [ ] Form submits successfully
- [ ] Workflow complete

---

## Test Case 8: All Users View Completed Form (READ-ONLY)

### Steps:
For each role (Supervisor, OM, BD, Procurement, GM):
1. Login
2. Navigate to Review History
3. Open the completed form

### Expected Results:
- [ ] All users see **Read-Only Mode** banner
- [ ] All previous reviewers' signatures visible
- [ ] No submit button for any user
- [ ] All data preserved and visible

---

## Test Case 9: Signature Visibility Test

### Verify:
- [ ] Supervisor signature visible to: OM, BD, Procurement, GM
- [ ] OM signature visible to: Supervisor (read-only), BD, Procurement, GM
- [ ] BD signature visible to: Supervisor, OM (read-only), Procurement, GM
- [ ] Procurement signature visible to: All users
- [ ] GM signature visible to: All users

---

## Test Case 10: PDF Generation Check

### Steps:
1. After any submission, click download PDF
2. Open the PDF

### Expected Results:
- [ ] All form data present
- [ ] All signatures visible in PDF
- [ ] All comments visible in PDF

---

## Quick Checklist Summary

| Feature | Working? |
|---------|----------|
| Supervisor can submit new form | [ ] |
| OM can review and sign | [ ] |
| BD can review and sign | [ ] |
| Procurement can review and sign | [ ] |
| GM can review and sign | [ ] |
| Supervisor sees OM signature after OM signs | [ ] |
| Supervisor sees READ-ONLY after OM signs | [ ] |
| OM sees READ-ONLY after BD signs | [ ] |
| All signatures cascade to subsequent reviewers | [ ] |
| "Form signed" indicator shows | [ ] |
| Timestamps displayed | [ ] |
| PDF/Excel downloads work | [ ] |
| No duplicate signatures | [ ] |

---

## Notes

- If any test fails, note the console error and browser behavior
- Take screenshots of any issues
- Check browser console (F12) for JavaScript errors

---

*Test Plan Created: Jan 25, 2026*
*Modules: Cleaning, Civil, HVAC&MEP (same workflow)*
