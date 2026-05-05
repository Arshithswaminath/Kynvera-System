# 🔄 Workflow Redesign - Complete Implementation Plan

**Date**: 2026-01-17  
**Status**: 📋 Planning Complete → Implementation in Progress

---

## 🎯 Overview

Complete redesign of the workflow system with the following changes:

### **1. Terminology Changes**
- ❌ Remove: "Technician"  
- ✅ Replace with: "Supervisor"

### **2. Workflow Stages & Progression Messages**

**Stage 1: Supervisor**
- Signs form
- After signing, sees message:  
  *"✅ Form signed! This will now be sent to: Operations Manager → Business Development & Procurement → General Manager"*

**Stage 2: Operations Manager**
- Sees: Supervisor's signature (already signed, view-only)
- Can: Add comments + Sign
- Can: Edit any form fields if needed
- After signing, sees message:  
  *"✅ Form approved! This will now be sent to: Business Development & Procurement → General Manager"*

**Stage 3a: Business Development**
- Sees: Supervisor + Operations Manager signatures (view-only)
- Can: Add comments + Sign
- Can: Edit any form fields if needed
- After signing, sees message:  
  *"✅ Form approved! Waiting for Procurement approval. After both approvals, this goes to General Manager."*

**Stage 3b: Procurement** (Parallel with BD)
- Sees: Supervisor + Operations Manager signatures (view-only)
- Can: Add comments + Sign
- Can: Edit any form fields if needed
- After signing, sees message:  
  *"✅ Form approved! Waiting for Business Development approval. After both approvals, this goes to General Manager."*

**Stage 4: General Manager**
- Sees: All previous signatures (Supervisor, Ops Manager, BD, Procurement)
- Can: Add comments + Sign (final approval)
- Can: Edit any form fields if needed
- After signing, sees message:  
  *"✅ FINAL APPROVAL COMPLETE! Form workflow finished."*

### **3. New "Submitted Forms" Module for Supervisors**

**Purpose**: Allow supervisors to:
- View all forms they've submitted
- See current status of each form
- Edit and resubmit forms if needed
- Track workflow progress

**Features**:
- List view with status badges
- Click to view/edit
- Resubmit button
- Status tracking:
  - ⏳ Pending (at Operations Manager)
  - 🔄 In Review (at BD/Procurement)
  - ✅ Approved (final)
  - ❌ Rejected (if applicable)

---

## 📋 Implementation Tasks

### **Phase 1: Update All Form Templates** ✅

**Files to Update**:
1. `module_hvac_mep/templates/hvac_mep_form.html`
2. `module_civil/templates/civil_form.html`
3. `module_cleaning/templates/cleaning_form.html`

**Changes for Each**:
- [ ] Replace "TECHNICIAN SIGNATURE" with "SUPERVISOR SIGNATURE"
- [ ] Replace "techSignature" variables with "supervisorSignature"
- [ ] Update all `tech_signature` references to `supervisor_signature`
- [ ] Add progression messages after each signature
- [ ] Show previous signatures as view-only
- [ ] Enable form editing for all workflow stages

### **Phase 2: Update Backend Routes** ✅

**Files to Update**:
1. `module_hvac_mep/routes.py`
2. `module_civil/routes.py`
3. `module_cleaning/routes.py`

**Changes**:
- [ ] Update field names from `tech_signature` to `supervisor_signature`
- [ ] Add workflow progression logic
- [ ] Add edit permission checks for all stages
- [ ] Update database field mappings

### **Phase 3: Update PDF/Excel Generators** ✅

**Files to Update**:
1. `module_hvac_mep/hvac_generators.py`
2. `module_civil/civil_generators.py`
3. `module_cleaning/cleaning_generators.py`

**Changes**:
- [ ] Change "Technician" labels to "Supervisor"
- [ ] Update signature field names
- [ ] Include all signatures in reports

### **Phase 4: Update Workflow System** ✅

**Files to Update**:
1. `app/workflow/routes.py`
2. `app/models.py`

**Changes**:
- [ ] Remove "technician" references
- [ ] Update workflow stage names
- [ ] Add progression messages API
- [ ] Enable editing at all stages

### **Phase 5: Create "Submitted Forms" Module** ✅

**New Features**:
1. **Dashboard Module Card**:
   - Icon: 📄
   - Title: "Submitted Forms"
   - Description: "View and manage your submitted inspection forms"
   - Visible only to Supervisors

2. **Submitted Forms Page**:
   - List all forms by supervisor
   - Status badges
   - Edit/resubmit functionality
   - Search and filter

3. **Files to Create/Update**:
   - [ ] `templates/submitted_forms.html` (new)
   - [ ] `templates/dashboard.html` (add module card)
   - [ ] `app/routes.py` or new blueprint (API endpoints)

### **Phase 6: Update Admin Dashboard** ✅

**File**: `templates/admin_dashboard.html`

**Changes**:
- [ ] Update designation displays
- [ ] Update workflow status labels

---

## 🔄 Workflow Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ 1. SUPERVISOR                                               │
│    • Creates form                                           │
│    • Signs                                                  │
│    • Message: "Sent to Ops Manager → BD & Proc → GM"       │
└─────────────┬───────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. OPERATIONS MANAGER                                       │
│    • Views Supervisor's signature ✓                         │
│    • Can edit form if needed                                │
│    • Adds comments + Signs                                  │
│    • Message: "Sent to BD & Procurement → GM"               │
└─────────────┬───────────────────────────────────────────────┘
              ↓
┌──────────────────────────────┐  ┌──────────────────────────┐
│ 3a. BUSINESS DEVELOPMENT     │  │ 3b. PROCUREMENT          │
│    • Views Sup + Ops Mgr ✓   │  │    • Views Sup + Ops ✓   │
│    • Can edit form           │  │    • Can edit form       │
│    • Comments + Signs        │  │    • Comments + Signs    │
│    • "Waiting for Proc..."   │  │    • "Waiting for BD..." │
└──────────────┬───────────────┘  └──────────┬───────────────┘
               └──────────┬───────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. GENERAL MANAGER                                          │
│    • Views all signatures: Sup, Ops, BD, Proc ✓            │
│    • Can edit form if needed                                │
│    • Adds comments + Signs (FINAL)                          │
│    • Message: "FINAL APPROVAL COMPLETE!"                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Dashboard Changes

### **Supervisor Dashboard**

**BEFORE**:
```
┌──────────┐  ┌──────────┐  ┌──────────┐
│ HVAC     │  │ Civil    │  │ Cleaning │
└──────────┘  └──────────┘  └──────────┘
```

**AFTER**:
```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│Submitted │  │ HVAC     │  │ Civil    │  │ Cleaning │
│ Forms    │  │          │  │          │  │          │
│ 📄 [5]  │  │          │  │          │  │          │
└──────────┘  └──────────┘  └──────────┘  └──────────┘
```

### **Reviewer Dashboards** (Ops Manager, BD, Procurement, GM)

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ Pending  │  │ HVAC     │  │ Civil    │  │ Cleaning │
│ Review   │  │          │  │          │  │          │
│ 📋 [3]  │  │          │  │          │  │          │
└──────────┘  └──────────┘  └──────────┘  └──────────┘
```

---

## 🎨 UI Components

### **1. Signature Section Template**

```html
<!-- Supervisor Signature (Stage 1) -->
<div class="signature-section">
  <label>SUPERVISOR SIGNATURE <span class="required">*</span></label>
  <canvas id="supervisorSignaturePad"></canvas>
  <button type="button" onclick="clearSignature('supervisor')">Clear</button>
</div>

<!-- Operations Manager View (Stage 2) -->
<div class="signature-section">
  <label>SUPERVISOR SIGNATURE <span class="badge bg-success">✓ Signed</span></label>
  <img src="{{ supervisor_signature_url }}" alt="Supervisor Signature" class="signature-display"/>
  <div class="signature-info">
    <small>Signed by: {{ supervisor_name }}</small>
    <small>Date: {{ supervisor_signed_date }}</small>
  </div>
</div>

<div class="signature-section">
  <label>OPERATIONS MANAGER SIGNATURE <span class="required">*</span></label>
  <textarea name="opman_comments" placeholder="Add your review comments..."></textarea>
  <canvas id="opmanSignaturePad"></canvas>
  <button type="button" onclick="clearSignature('opman')">Clear</button>
</div>
```

### **2. Progression Message**

```html
<div class="workflow-progression-message" style="display: none;" id="progressionMessage">
  <div class="alert alert-success">
    <strong>✅ Form Signed Successfully!</strong>
    <p id="progressionText"></p>
  </div>
</div>
```

**JavaScript**:
```javascript
function showProgressionMessage(stage) {
  const messages = {
    'supervisor': 'This form will now be sent to:<br>→ Operations Manager<br>→ Business Development & Procurement<br>→ General Manager',
    'operations_manager': 'This form will now be sent to:<br>→ Business Development & Procurement<br>→ General Manager',
    'business_development': 'Waiting for Procurement approval. After both approvals, this goes to General Manager.',
    'procurement': 'Waiting for Business Development approval. After both approvals, this goes to General Manager.',
    'general_manager': 'FINAL APPROVAL COMPLETE! Form workflow finished.'
  };
  
  document.getElementById('progressionText').innerHTML = messages[stage];
  document.getElementById('progressionMessage').style.display = 'block';
}
```

---

## 📝 Database Changes

### **Update Field Names**

**FROM**:
- `tech_signature` → `supervisor_signature`
- `technician_id` → `supervisor_id`
- `technician_signed_at` → `supervisor_signed_at`

**TO**: Already correct in models (uses `supervisor`)

---

## ✅ Implementation Priority

**Priority 1** (Critical):
1. ✅ Update form templates (remove "Technician", add "Supervisor")
2. ✅ Update backend routes (field name changes)
3. ✅ Test basic submission flow

**Priority 2** (High):
4. Add progression messages after each signature
5. Show previous signatures as view-only
6. Enable form editing at all stages

**Priority 3** (Medium):
7. Create "Submitted Forms" module for supervisors
8. Add status tracking
9. Add edit/resubmit functionality

**Priority 4** (Nice to have):
10. Add workflow progress visualization
11. Add email notifications
12. Add audit log

---

## 🧪 Testing Checklist

### **Forms**
- [ ] "Technician" completely removed from all forms
- [ ] "Supervisor" appears correctly in all forms
- [ ] Signature pads work for all roles
- [ ] Previous signatures display correctly

### **Workflow**
- [ ] Supervisor can sign and submit
- [ ] Operations Manager sees supervisor signature
- [ ] BD/Procurement see previous signatures
- [ ] General Manager sees all signatures
- [ ] Progression messages appear correctly

### **Editing**
- [ ] Operations Manager can edit form
- [ ] BD can edit form
- [ ] Procurement can edit form
- [ ] General Manager can edit form
- [ ] Edits are saved correctly

### **Submitted Forms Module**
- [ ] Module appears only for supervisors
- [ ] Lists all supervisor's forms
- [ ] Status badges display correctly
- [ ] Edit/resubmit works
- [ ] Search/filter works

---

## 📚 Documentation Updates Needed

- [ ] Update user manual
- [ ] Update API documentation
- [ ] Update workflow diagrams
- [ ] Update training materials

---

**Status**: 📋 **Plan Complete - Ready for Implementation**  
**Est. Time**: 2-3 hours for full implementation  
**Complexity**: High (multiple files, workflow logic, new module)

**Next Step**: Begin Phase 1 - Update Form Templates
