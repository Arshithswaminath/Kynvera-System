# Implementation Status - HVAC/MEP and Civil Forms

## Goal
Match the Cleaning form's master behavior and UI exactly in both HVAC/MEP and Civil forms.

## Current Status (HVAC/MEP)

### ✅ Completed
1. **Fixed supervisor section condition** - Only shows to actual supervisor users
2. **Fixed duplicate supervisor section** - Removed incorrect conditional rendering
3. **Added "Supervisor Sign-off" heading** - Matches Cleaning form
4. **Added supervisor review section styling** - Border-top, proper padding, color scheme
5. **Added "Previous Reviews" section for Supervisor** - Shows OM/BD/Procurement/GM reviews
6. **Added "Previous Reviews" section for OM** - Shows Supervisor/BD/Procurement reviews
7. **Added read-only sections** for BD, Procurement, GM to view earlier reviewers
8. **Fixed JavaScript error** - Added null checks for dropZone and curPhotos
9. **Added debugging logs** - To track supervisor signature loading for OM

### ⚠️ Partially Complete
1. **JavaScript to load supervisor's "Previous Reviews" data** - Needs full implementation from Cleaning form
   - Location in Cleaning: Lines 2573-2840
   - Needs: Load OM, BD, Procurement, GM data for supervisor viewing

### ❌ To Do
1. **Copy complete JavaScript logic from Cleaning form** for:
   - Supervisor viewing OM/BD/Procurement/GM (lines 2573-2840 in Cleaning)
   - Same pattern already exists for OM viewing (lines 4734-4910 in HVAC/MEP)
2. **Test all scenarios** as per TEST_PLAN_COMPLETE.md
3. **Apply exact same fixes to Civil form**

---

## Implementation Plan for Remaining Work

### Step 1: HVAC/MEP JavaScript (Supervisor's Previous Reviews)
**Location:** After line ~4650 in `module_hvac_mep/templates/hvac_mep_form.html`  
**Action:** Copy the supervisor's previous reviewers loading logic from Cleaning form (lines 2573-2840)

**Pattern to follow:**
```javascript
{% if user_designation == 'supervisor' %}
// Load OM review for Supervisor
let omCommentsSupervisor = formData?.operations_manager_comments || submissionData?.operations_manager_comments;
let omSigSupervisor = formData?.operations_manager_signature || submissionData?.form_data?.operations_manager_signature;

if (omCommentsSupervisor || omSigSupervisor) {
  document.getElementById('opsManagerReadOnlySupervisor').style.display = 'block';
  document.getElementById('previousForSupervisorSection').style.display = 'block';
  // ... load comments, signature, timestamp
}

// Same pattern for BD, Procurement, GM
{% endif %}
```

### Step 2: Civil Form - Complete Restructure
**File:** `module_civil/templates/civil_form.html`

**Changes Needed:**
1. Change heading from current to "Supervisor Sign-off"
2. Add supervisor review section with proper styling (border-top, colors)
3. Add "Previous Reviews" sections for all roles (Supervisor, OM, BD, Procurement, GM)
4. Copy JavaScript logic from Cleaning form for all roles

**Files to Reference:**
- Source (Master): `module_cleaning/templates/cleaning_form.html`
- Target 1: `module_hvac_mep/templates/hvac_mep_form.html` (partially complete)
- Target 2: `module_civil/templates/civil_form.html` (needs work)

---

## Key Structural Elements (from Cleaning - Master)

### HTML Structure
```html
<h4 class="section-heading">Supervisor Sign-off</h4>

<!-- Supervisor's own section (editable) -->
{% if user_designation == 'supervisor' or (user and user.role == 'admin') %}
<div class="col-12 mb-3" style="border-top: 2px solid var(--primary); padding-top: 1.5rem; margin-top: 1rem;">
  <h5 style="color: var(--primary); margin-bottom: 1rem;">Supervisor Review</h5>
  <!-- Comments textarea -->
  <!-- Signature pad -->
</div>
{% endif %}

<!-- Previous Reviews for each role -->
{% if user_designation == 'supervisor' and is_edit_mode %}
<div class="col-12 mb-4" id="previousForSupervisorSection" style="display: none;">
  <div class="alert alert-info mb-3" style="background: #f0f9ff; border-color: #0ea5e9;">
    <strong>Previous Reviews</strong>
  </div>
  <!-- OM section -->
  <!-- BD section -->
  <!-- Procurement section -->
  <!-- GM section -->
</div>
{% endif %}

<!-- Same pattern for OM, BD, Procurement, GM, Admin -->
```

### JavaScript Pattern
```javascript
// For each role viewing previous reviewers:
{% if user_designation == 'ROLE' %}
// Extract data from formData or submissionData
let reviewerComments = formData?.reviewer_comments || submissionData?.reviewer_comments;
let reviewerSig = formData?.reviewer_signature || submissionData?.form_data?.reviewer_signature;

if (reviewerComments || reviewerSig) {
  section.style.display = 'block';
  prevSection.style.display = 'block';
  
  // Load timestamp (with formatSigningTime)
  // Load comments
  // Load signature (with displaySignatureInContainer)
}
{% endif %}
```

---

## Testing Checklist
- [ ] Supervisor signs → sees own signature with edit option
- [ ] OM views form → sees Supervisor in "Previous Reviews" with signature
- [ ] OM signs → Supervisor views form → sees OM in "Previous Reviews"
- [ ] BD views → sees Supervisor + OM
- [ ] Procurement views → sees all previous
- [ ] GM views → sees all previous
- [ ] UI matches Cleaning form exactly (styling, alignment, colors)

---

## Files Modified (This Session)
1. `d:\Work\Injaaz-App\module_hvac_mep\templates\hvac_mep_form.html`
   - Fixed supervisor section conditional
   - Added "Supervisor Sign-off" heading
   - Added styling to supervisor review section
   - Added "Previous Reviews" sections for Supervisor and OM
   - Fixed JavaScript errors (dropZone null check)
   - Added debugging logs for OM viewing supervisor data

2. `d:\Work\Injaaz-App\module_civil\templates\civil_form.html`
   - Added "Previous Reviews" section for OM
   - Added JavaScript to load BD/Procurement data for OM

3. `d:\Work\Injaaz-App\TEST_PLAN_COMPLETE.md` - Created comprehensive test plan

---

##Current Immediate Issue
**Problem:** When OM views the form after supervisor signs, the supervisor's signature and comments don't show in "Previous Reviews".

**Root Cause:** JavaScript isn't properly loading the supervisor data for OM to view.

**Status:** Debugging logs added. Waiting for console output to diagnose further.

**Next Action:** Review browser console logs and fix data loading logic based on output.
