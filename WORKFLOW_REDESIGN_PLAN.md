# Workflow Redesign Implementation Plan

## Overview
Redesigning the submission workflow to support a multi-stage approval process without technicians.

## New Workflow Stages

### 1. Stage 1: Supervisor/Inspector
- **Role**: `supervisor` (designation)
- **Actions**: Create form, fill details, submit for review
- **Permissions**: Create, Edit own submissions, Submit

### 2. Stage 2: Operations Manager  
- **Role**: `operations_manager` (designation)
- **Actions**: Review, Edit (if needed), Sign, Approve/Reject
- **Permissions**: View submitted forms, Edit, Sign, Forward to next stage

### 3. Stage 3: Business Development & Procurement (Parallel)
- **Roles**: `business_development`, `procurement` (designations)
- **Actions**: Review, Edit (if needed), Add comments
- **Permissions**: View forms approved by Ops Manager, Edit, Comment, Forward

### 4. Stage 4: General Manager
- **Role**: `general_manager` (designation)
- **Actions**: Final review, Edit (if needed), Final approval
- **Permissions**: View all forms, Edit, Final approval/rejection

### 5. Admin
- **Role**: `admin` (role)
- **Actions**: User management, Role assignment, System configuration
- **Permissions**: All permissions, Manage users, Assign roles

## Database Changes

### User Model Updates
```python
# Current designation field values: 'technician', 'supervisor', 'manager'
# New designation field values:
DESIGNATIONS = [
    'supervisor',          # Stage 1: Creates and submits forms
    'operations_manager',  # Stage 2: First approval
    'business_development',# Stage 3: Parallel review
    'procurement',         # Stage 3: Parallel review  
    'general_manager'      # Stage 4: Final approval
]

# role field remains: 'admin', 'user'
# designation determines workflow permissions
```

### Submission Model Updates
```python
# New workflow_status values:
WORKFLOW_STATUSES = [
    'submitted',                    # Created by supervisor
    'operations_manager_review',    # Sent to ops manager
    'operations_manager_approved',  # Approved by ops manager
    'bd_procurement_review',        # Sent to BD & Procurement
    'bd_approved',                  # BD approved
    'procurement_approved',         # Procurement approved
    'general_manager_review',       # Sent to GM
    'general_manager_approved',     # Final approval
    'completed',                    # Fully approved
    'rejected'                      # Rejected at any stage
]

# New fields needed:
operations_manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))
business_dev_id = db.Column(db.Integer, db.ForeignKey('users.id'))
procurement_id = db.Column(db.Integer, db.ForeignKey('users.id'))
general_manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))

operations_manager_signature = db.Column(db.Text)  # Base64 or URL
business_dev_signature = db.Column(db.Text)
procurement_signature = db.Column(db.Text)
general_manager_signature = db.Column(db.Text)

operations_manager_approved_at = db.Column(db.DateTime)
business_dev_approved_at = db.Column(db.DateTime)
procurement_approved_at = db.Column(db.DateTime)
general_manager_approved_at = db.Column(db.DateTime)

operations_manager_comments = db.Column(db.Text)
business_dev_comments = db.Column(db.Text)
procurement_comments = db.Column(db.Text)
general_manager_comments = db.Column(db.Text)

rejection_stage = db.Column(db.String(30))  # Which stage rejected
rejection_reason = db.Column(db.Text)
rejected_at = db.Column(db.DateTime)
rejected_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
```

## File Changes Required

### 1. Models (`app/models.py`)
- Update User model with new designations
- Update Submission model with new workflow fields
- Create migration script

### 2. Authentication (`app/auth/routes.py`)
- Update role checks
- Add designation-based permissions

### 3. Workflow Routes (`app/workflow/routes.py`)
- Create new approval endpoints for each stage
- Update dashboard to show role-appropriate submissions

### 4. Admin Routes (`app/admin/routes.py`)
- Update user creation/editing to support new roles
- Add role assignment interface

### 5. Form Templates (all modules)
- Update signature sections for all stages
- Add comment fields for each approver
- Update form display based on user designation

### 6. Dashboard (`templates/dashboard.html`)
- Show submissions relevant to user's designation
- Display workflow status clearly

## Implementation Steps

1. ✅ Create this planning document
2. ⏳ Update database models
3. ⏳ Create migration script
4. ⏳ Update workflow routes
5. ⏳ Update admin panel
6. ⏳ Update form templates
7. ⏳ Update dashboards
8. ⏳ Test complete workflow

## Migration Strategy

### Option 1: Clean Migration (Recommended for Development)
- Drop existing workflow data
- Apply new schema
- Create fresh test users

### Option 2: Data Preservation (Production)
- Map existing technician → supervisor
- Map existing supervisor → operations_manager
- Map existing manager → general_manager
- Set other roles as null (to be assigned by admin)

## API Endpoints

### New Workflow Endpoints

```
POST /api/workflow/submissions/<id>/approve-ops-manager
POST /api/workflow/submissions/<id>/approve-bd
POST /api/workflow/submissions/<id>/approve-procurement  
POST /api/workflow/submissions/<id>/approve-gm
POST /api/workflow/submissions/<id>/reject
GET  /api/workflow/dashboard/<designation>
```

### Admin Endpoints

```
POST   /api/admin/users/<id>/assign-designation
GET    /api/admin/users/by-designation/<designation>
```

## Security Considerations

1. Each role can only access submissions at their stage
2. Admins can view all but should not interfere with workflow
3. Rejection moves back to supervisor for revision
4. Audit log all approvals and rejections

## UI Updates

### Dashboard Views by Role

**Supervisor:**
- My Submissions
- Draft Submissions
- Rejected Submissions (to revise)
- Create New Submission

**Operations Manager:**
- Pending My Review
- Approved by Me
- Rejected by Me

**Business Development / Procurement:**
- Pending My Review
- Approved by Me

**General Manager:**
- Pending Final Approval
- Approved Submissions
- All Submissions (read-only history)

**Admin:**
- User Management
- Role Assignment
- System Statistics
- All Submissions (admin view)

## Form Signature Sections

Each form will show signatures progressively:

```
1. Supervisor/Inspector: _____________ (Date)
2. Operations Manager: _____________ (Date) [Comment: _____]
3. Business Development: _____________ (Date) [Comment: _____]
4. Procurement: _____________ (Date) [Comment: _____]
5. General Manager: _____________ (Date) [Comment: _____]
```

## Next Steps

After approval of this plan:
1. Implement database changes
2. Update backend routes
3. Update frontend forms
4. Create migration scripts
5. Test thoroughly
6. Deploy

---

**Status**: Planning Complete - Awaiting Approval to Implement
**Created**: 2026-01-17
**Last Updated**: 2026-01-17
