# Form Templates Update Guide
## Implementing New 5-Stage Workflow in Forms

This document provides step-by-step instructions for updating all form templates (Civil, HVAC/MEP, Cleaning) to support the new 5-stage approval workflow.

## Overview

The new workflow requires forms to:
1. Support multiple approval stages with different signature/comment sections
2. Show/hide UI elements based on user designation and workflow status
3. Handle approval/rejection actions at each stage
4. Display workflow progress to users

## Files Already Created

### ✅ Completed Resources

1. **`templates/workflow_signatures.html`**
   - Reusable signature component for all stages
   - Includes HTML, CSS, and JavaScript
   - Ready to be included in form templates

2. **`static/workflow_manager.js`**
   - Centralized JavaScript class for workflow management
   - Handles approval logic for all stages
   - Manages signature pads and validation

3. **Database Models** (`app/models.py`)
   - Updated with all new workflow fields
   - Supports 5 designations and tracking for each stage

4. **Backend Routes** (`app/workflow/routes.py`)
   - Complete API endpoints for all approval stages
   - Rejection handling and workflow progression

5. **Admin Panel** (`app/admin/routes.py`)
   - Designation management endpoints
   - User listing by designation
   - Workflow statistics

6. **Dashboard** (`templates/dashboard.html`)
   - Role-specific submission display
   - Updated for all 5 designations
   - Workflow progress indicators

## Form Template Update Steps

### Step 1: Include Workflow Resources

Add to each form's `<head>` section:

```html
<!-- Workflow Management -->
<script src="{{ url_for('static', filename='workflow_manager.js') }}"></script>
<link rel="stylesheet" href="{{ url_for('static', filename='workflow_styles.css') }}">
```

### Step 2: Replace Signature Section

**Find** the existing signature section (usually near the end of the form):
```html
<!-- Old technician/supervisor signature sections -->
<div id="techSignature">...</div>
<div id="supervisorSignature">...</div>
```

**Replace** with:
```html
<!-- New Multi-Stage Workflow Signatures -->
{% include 'workflow_signatures.html' %}
```

### Step 3: Initialize Workflow Manager

Add to the form's JavaScript initialization:

```javascript
// Initialize workflow manager
let workflowManager;

document.addEventListener('DOMContentLoaded', function() {
    const user = JSON.parse(localStorage.getItem('user'));
    const submissionId = getSubmissionIdFromURL(); // Your existing function
    
    // Initialize workflow manager
    workflowManager = new WorkflowManager(
        submissionId,
        user?.designation,
        user?.role
    );
    
    workflowManager.init();
    
    // Load submission data if in review mode
    if (isReviewMode()) {
        loadSubmissionForReview();
    }
});
```

### Step 4: Update Form Submission Logic

**For Supervisors (Initial Submission):**

```javascript
async function submitForm() {
    // Validate form
    if (!validateForm()) {
        alert('Please fill all required fields');
        return;
    }
    
    // Get supervisor signature
    const supervisorSig = workflowManager.getPads().supervisorPad;
    if (!supervisorSig || supervisorSig.isEmpty()) {
        alert('Please provide your signature');
        return;
    }
    
    const formData = collectFormData();
    formData.supervisor_signature = supervisorSig.toDataURL();
    
    // Submit to backend
    const response = await fetch(`/api/${moduleName}/submit-with-urls`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify(formData)
    });
    
    const result = await response.json();
    
    if (result.success) {
        alert('✅ Form submitted successfully!');
        // Automatically move to Operations Manager review
        await updateWorkflowStatus(result.submission_id, 'operations_manager_review');
        window.location.href = '/dashboard';
    } else {
        alert('❌ Submission failed: ' + result.error);
    }
}
```

**For Reviewers (Operations Manager, BD, Procurement, GM):**

The `WorkflowManager` class handles all review/approval actions automatically. Just ensure the signature sections are visible based on user designation.

### Step 5: Update Load Submission Logic

When loading a submission for review:

```javascript
async function loadSubmissionForReview() {
    const submissionId = new URLSearchParams(window.location.search).get('edit');
    const token = localStorage.getItem('access_token');
    
    const response = await fetch(`/api/workflow/submissions/${submissionId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    
    const data = await response.json();
    const submission = data.data || data;
    
    // Populate form fields
    populateFormFields(submission.form_data);
    
    // Update workflow UI
    workflowManager.updateWorkflowUI(submission.workflow_status);
    
    // Load existing signatures if present
    loadExistingSignatures(submission.form_data);
    
    // Show appropriate approval section based on workflow status
    // (This is handled automatically by workflowManager.updateWorkflowUI)
}
```

### Step 6: Add Workflow Status Display

Add near the submit button:

```html
<div id="workflowStatusContainer" class="mt-4">
    <!-- Automatically populated by workflow_signatures.html -->
</div>
```

### Step 7: Handle Rejection Workflow

When a submission is rejected, it goes back to the supervisor. Add logic to handle resubmission:

```javascript
function checkIfRejected(submission) {
    if (submission.workflow_status === 'rejected') {
        // Show rejection reason
        const rejectionAlert = document.createElement('div');
        rejectionAlert.className = 'alert alert-warning';
        rejectionAlert.innerHTML = `
            <h4>⚠️ This submission was rejected</h4>
            <p><strong>Reason:</strong> ${submission.rejection_reason}</p>
            <p><strong>Rejected at:</strong> ${submission.rejection_stage}</p>
            <p>Please make the necessary changes and resubmit.</p>
        `;
        document.getElementById('formContainer').prepend(rejectionAlert);
        
        // Enable form for editing
        enableFormEditing();
    }
}
```

### Step 8: Update Backend Routes

Each module's routes need minor updates:

**Example for Civil Module (`module_civil/routes.py`):**

```python
@civil_bp.route('/submit-with-urls', methods=['POST'])
@jwt_required()
def submit_with_urls():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        # Check if user is supervisor
        if user.designation != 'supervisor' and user.role != 'admin':
            return error_response(
                'Only supervisors can create new submissions',
                status_code=403
            )
        
        data = request.get_json()
        
        # ... validate and process data ...
        
        # Create submission
        submission = create_submission_db(
            user_id=user_id,
            module_type='civil',
            site_name=data.get('site_name'),
            visit_date=visit_date,
            form_data=data
        )
        
        # Set initial workflow status
        submission.workflow_status = 'operations_manager_review'
        submission.supervisor_id = user_id
        db.session.commit()
        
        # ... create job for report generation ...
        
        return success_response({
            'submission_id': submission.submission_id,
            'workflow_status': submission.workflow_status,
            'message': 'Submitted successfully. Sent to Operations Manager for review.'
        })
    except Exception as e:
        logger.error(f"Error submitting: {e}")
        return error_response('Submission failed', status_code=500)
```

## Module-Specific Implementation

### Civil Form (`module_civil/templates/civil_form.html`)

**Current Status:**
- Has single signature for technician/supervisor
- Uses simple submit workflow

**Changes Needed:**
1. Include `workflow_signatures.html`
2. Initialize `WorkflowManager`
3. Update submit button to check user designation
4. Add workflow status display
5. Handle review mode appropriately

### HVAC/MEP Form (`module_hvac_mep/templates/hvac_mep_form.html`)

**Current Status:**
- Has technician and operations manager signatures
- Uses tab-based navigation

**Changes Needed:**
1. Replace existing signature tabs with `workflow_signatures.html`
2. Add workflow progress to tab navigation
3. Initialize `WorkflowManager` after tabs are loaded
4. Update signature handling in `submitAll()` function
5. Add stage-specific validation

### Cleaning Form (`module_cleaning/templates/cleaning_form.html`)

**Current Status:**
- Recently updated to supervisor workflow
- Uses simple signature section

**Changes Needed:**
1. Include `workflow_signatures.html`
2. Initialize `WorkflowManager`
3. Replace current signature section
4. Add workflow progress indicator
5. Update load/submit logic

## Testing Checklist

### Create Test Users

```sql
-- Supervisor
INSERT INTO users (username, email, password_hash, designation, role, is_active)
VALUES ('supervisor1', 'supervisor@injaaz.com', '<hash>', 'supervisor', 'user', true);

-- Operations Manager
INSERT INTO users (username, email, password_hash, designation, role, is_active)
VALUES ('ops_mgr1', 'ops@injaaz.com', '<hash>', 'operations_manager', 'user', true);

-- Business Development
INSERT INTO users (username, email, password_hash, designation, role, is_active)
VALUES ('bd1', 'bd@injaaz.com', '<hash>', 'business_development', 'user', true);

-- Procurement
INSERT INTO users (username, email, password_hash, designation, role, is_active)
VALUES ('procurement1', 'procurement@injaaz.com', '<hash>', 'procurement', 'user', true);

-- General Manager
INSERT INTO users (username, email, password_hash, designation, role, is_active)
VALUES ('gm1', 'gm@injaaz.com', '<hash>', 'general_manager', 'user', true);
```

### Test Workflow

1. **As Supervisor:**
   - ✅ Create new Civil form
   - ✅ Fill all fields and add photos
   - ✅ Sign and submit
   - ✅ Verify submission goes to Operations Manager review

2. **As Operations Manager:**
   - ✅ See submission in pending list
   - ✅ Open for review
   - ✅ Edit fields if needed
   - ✅ Add comments
   - ✅ Sign and approve
   - ✅ Verify moves to BD/Procurement

3. **As Business Development:**
   - ✅ See submission in pending list
   - ✅ Review and add comments
   - ✅ Approve
   - ✅ Verify stays at BD/Procurement until Procurement also approves

4. **As Procurement:**
   - ✅ See submission in pending list
   - ✅ Review and add comments
   - ✅ Approve
   - ✅ Verify moves to General Manager review

5. **As General Manager:**
   - ✅ See submission in pending list
   - ✅ Final review
   - ✅ Sign and approve
   - ✅ Verify status changes to 'completed'

6. **Rejection Test:**
   - ✅ As any approver, reject a submission
   - ✅ Verify supervisor sees rejection reason
   - ✅ Supervisor edits and resubmits
   - ✅ Verify workflow restarts from Operations Manager

## Common Issues and Solutions

### Issue 1: Signature Pad Not Initializing

**Solution:**
```javascript
// Ensure SignaturePad library is loaded before WorkflowManager
<script src="https://cdn.jsdelivr.net/npm/signature_pad@4.0.0/dist/signature_pad.umd.min.js"></script>
<script src="{{ url_for('static', filename='workflow_manager.js') }}"></script>
```

### Issue 2: Wrong Section Showing

**Problem:** Operations Manager section shows when user is Supervisor

**Solution:**
```javascript
// Check user designation matches workflow status
workflowManager.updateWorkflowUI(workflowStatus);
// This automatically shows/hides correct sections
```

### Issue 3: Approval Not Working

**Problem:** Clicking approve button does nothing

**Solution:**
1. Check browser console for errors
2. Verify JWT token is valid
3. Ensure `submissionId` is correctly set
4. Check backend logs for API errors

### Issue 4: Photos Not Showing in Review

**Problem:** Photos don't load when reviewing submission

**Solution:**
```javascript
// In loadSubmissionForReview(), ensure photos are loaded
if (submission.form_data.photos && Array.isArray(submission.form_data.photos)) {
    submission.form_data.photos.forEach(photoUrl => {
        displayPhoto(photoUrl);
    });
}
```

## API Reference

### Workflow Endpoints

```
GET    /api/workflow/submissions/pending          - Get submissions pending for current user
GET    /api/workflow/submissions/{id}              - Get submission details
GET    /api/workflow/submissions/history           - Get user's reviewed submissions

POST   /api/workflow/submissions/{id}/approve-ops-manager   - Ops Manager approval
POST   /api/workflow/submissions/{id}/approve-bd            - BD approval
POST   /api/workflow/submissions/{id}/approve-procurement   - Procurement approval  
POST   /api/workflow/submissions/{id}/approve-gm            - GM final approval
POST   /api/workflow/submissions/{id}/reject                - Reject at any stage
POST   /api/workflow/submissions/{id}/resubmit              - Resubmit after rejection
PUT    /api/workflow/submissions/{id}/update                - Update form data
```

### Request/Response Examples

**Approve as Operations Manager:**
```json
POST /api/workflow/submissions/CIV-2026-001/approve-ops-manager

Request:
{
    "comments": "Approved with minor notes",
    "signature": "data:image/png;base64,...",
    "form_data": {
        // Any updated fields
    }
}

Response:
{
    "success": true,
    "message": "Approved successfully. Forwarded to Business Development and Procurement.",
    "data": {
        "submission": { ... }
    }
}
```

**Reject Submission:**
```json
POST /api/workflow/submissions/CIV-2026-001/reject

Request:
{
    "reason": "Photos are unclear. Please retake."
}

Response:
{
    "success": true,
    "message": "Submission rejected and sent back to supervisor for revision.",
    "data": {
        "submission": { ... }
    }
}
```

## PDF/Excel Report Generation

The new workflow requires updates to report generators to include all signatures:

### PDF Reports

```python
# In module generators (e.g., civil_generators.py)

def create_pdf_report(data, submission_record):
    # ... existing setup ...
    
    # Signatures section - all stages
    signatures_data = []
    
    # Supervisor
    if data.get('supervisor_signature'):
        signatures_data.append({
            'title': 'Supervisor/Inspector',
            'signature': data['supervisor_signature'],
            'name': submission_record.supervisor.full_name if submission_record.supervisor else 'N/A',
            'date': submission_record.created_at
        })
    
    # Operations Manager
    if submission_record.operations_manager_id and data.get('operations_manager_signature'):
        signatures_data.append({
            'title': 'Operations Manager',
            'signature': data['operations_manager_signature'],
            'name': submission_record.operations_manager.full_name,
            'date': submission_record.operations_manager_approved_at,
            'comments': submission_record.operations_manager_comments
        })
    
    # General Manager
    if submission_record.general_manager_id and data.get('general_manager_signature'):
        signatures_data.append({
            'title': 'General Manager',
            'signature': data['general_manager_signature'],
            'name': submission_record.general_manager.full_name,
            'date': submission_record.general_manager_approved_at,
            'comments': submission_record.general_manager_comments
        })
    
    add_signatures_section(story, signatures_data, styles)
    
    # ... rest of PDF generation ...
```

### Excel Reports

Excel reports should NOT include signatures, only data fields and comments:

```python
# In module generators
def create_excel_report(data, submission_record):
    # ... existing setup ...
    
    # Add approval comments section (no signatures)
    if submission_record.operations_manager_comments:
        ws.append(['Operations Manager Comments:', submission_record.operations_manager_comments])
    
    if submission_record.business_dev_comments:
        ws.append(['Business Development Comments:', submission_record.business_dev_comments])
    
    if submission_record.procurement_comments:
        ws.append(['Procurement Comments:', submission_record.procurement_comments])
    
    if submission_record.general_manager_comments:
        ws.append(['General Manager Comments:', submission_record.general_manager_comments])
    
    # ... rest of Excel generation ...
```

## Migration from Old Workflow

If you have existing submissions with the old workflow:

```sql
-- Map old designations to new ones
UPDATE users SET designation = 'supervisor' WHERE designation = 'technician';
UPDATE users SET designation = 'operations_manager' WHERE designation = 'supervisor' OR designation = 'manager';

-- Update existing submissions
UPDATE submissions 
SET workflow_status = 'operations_manager_review' 
WHERE workflow_status IN ('submitted', 'supervisor_notified');

UPDATE submissions 
SET workflow_status = 'completed' 
WHERE workflow_status = 'approved';
```

## Summary

This guide provides everything needed to update forms for the new 5-stage workflow. The key is to:

1. Use the reusable `workflow_signatures.html` component
2. Initialize `WorkflowManager` for each form
3. Update backend routes to handle new workflow statuses
4. Test thoroughly with users in each role

All supporting files (models, routes, dashboard) have already been updated. The remaining work is updating the three form templates following this guide.

---

**Status**: Guide Complete - Ready for Form Implementation
**Created**: 2026-01-17
**Last Updated**: 2026-01-17
