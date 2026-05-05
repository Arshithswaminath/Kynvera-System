/**
 * Workflow Manager - 5-Stage Approval System
 * Handles workflow progression, approvals, and rejections
 * 
 * Dependencies: api-client.js (for authenticated API calls)
 */

class WorkflowManager {
    constructor(submissionId, userDesignation, userRole) {
        this.submissionId = submissionId;
        this.userDesignation = userDesignation;
        this.userRole = userRole;
        this.currentStatus = null;
        this.signaturePads = {};
    }

    /**
     * Initialize signature pads for the current user's stage
     */
    initializeSignaturePads() {
        // Supervisor pad (always available for initial submission)
        const supervisorCanvas = document.getElementById('supervisorSignaturePad');
        if (supervisorCanvas) {
            this.signaturePads.supervisor = new SignaturePad(supervisorCanvas, {
                backgroundColor: 'rgb(255, 255, 255)',
                penColor: 'rgb(0, 0, 0)'
            });
            
            const clearBtn = document.getElementById('clearSupervisor');
            if (clearBtn) {
                clearBtn.addEventListener('click', () => {
                    this.signaturePads.supervisor.clear();
                });
            }
        }

        // Operations Manager pad
        const opsMgrCanvas = document.getElementById('opsMgrSignaturePad');
        if (opsMgrCanvas && this.userDesignation === 'operations_manager') {
            this.signaturePads.opsMgr = new SignaturePad(opsMgrCanvas, {
                backgroundColor: 'rgb(255, 255, 255)',
                penColor: 'rgb(0, 0, 0)'
            });
            
            const clearBtn = document.getElementById('clearOpsMgr');
            if (clearBtn) {
                clearBtn.addEventListener('click', () => {
                    this.signaturePads.opsMgr.clear();
                });
            }
        }

        // General Manager pad
        const gmCanvas = document.getElementById('gmSignaturePad');
        if (gmCanvas && this.userDesignation === 'general_manager') {
            this.signaturePads.gm = new SignaturePad(gmCanvas, {
                backgroundColor: 'rgb(255, 255, 255)',
                penColor: 'rgb(0, 0, 0)'
            });
            
            const clearBtn = document.getElementById('clearGM');
            if (clearBtn) {
                clearBtn.addEventListener('click', () => {
                    this.signaturePads.gm.clear();
                });
            }
        }

        console.log('✅ Signature pads initialized for', this.userDesignation);
    }

    /**
     * Setup approval button handlers
     */
    setupApprovalHandlers() {
        // Operations Manager approval
        const btnApproveOpsMgr = document.getElementById('btnApproveOpsMgr');
        if (btnApproveOpsMgr) {
            btnApproveOpsMgr.addEventListener('click', () => {
                this.approveAsOperationsManager();
            });
        }

        const btnRejectOpsMgr = document.getElementById('btnRejectOpsMgr');
        if (btnRejectOpsMgr) {
            btnRejectOpsMgr.addEventListener('click', () => {
                this.showRejectionModal();
            });
        }

        // Business Development approval
        const btnApproveBD = document.getElementById('btnApproveBD');
        if (btnApproveBD) {
            btnApproveBD.addEventListener('click', () => {
                this.approveAsBusinessDevelopment();
            });
        }

        const btnRejectBD = document.getElementById('btnRejectBD');
        if (btnRejectBD) {
            btnRejectBD.addEventListener('click', () => {
                this.showRejectionModal();
            });
        }

        // Procurement approval
        const btnApproveProcurement = document.getElementById('btnApproveProcurement');
        if (btnApproveProcurement) {
            btnApproveProcurement.addEventListener('click', () => {
                this.approveAsProcurement();
            });
        }

        const btnRejectProcurement = document.getElementById('btnRejectProcurement');
        if (btnRejectProcurement) {
            btnRejectProcurement.addEventListener('click', () => {
                this.showRejectionModal();
            });
        }

        // General Manager approval
        const btnApproveGM = document.getElementById('btnApproveGM');
        if (btnApproveGM) {
            btnApproveGM.addEventListener('click', () => {
                this.approveAsGeneralManager();
            });
        }

        const btnRejectGM = document.getElementById('btnRejectGM');
        if (btnRejectGM) {
            btnRejectGM.addEventListener('click', () => {
                this.showRejectionModal();
            });
        }

        // Rejection modal confirm button
        const confirmReject = document.getElementById('confirmReject');
        if (confirmReject) {
            confirmReject.addEventListener('click', () => {
                this.confirmRejection();
            });
        }

        console.log('✅ Approval handlers setup for', this.userDesignation);
    }

    /**
     * Operations Manager approval
     */
    async approveAsOperationsManager() {
        try {
            const comments = document.getElementById('opsMgrComments')?.value || '';
            const signature = this.signaturePads.opsMgr ? this.signaturePads.opsMgr.toDataURL() : '';

            if (this.signaturePads.opsMgr && this.signaturePads.opsMgr.isEmpty()) {
                alert('Please provide your signature before approving.');
                return;
            }

            // Get form data updates if any
            const formDataUpdates = this.collectFormDataUpdates();

            const response = await ApiClient.post(
                `/api/workflow/submissions/${this.submissionId}/approve-ops-manager`,
                {
                    comments: comments,
                    signature: signature,
                    form_data: formDataUpdates
                },
                false // Don't auto-redirect, handle manually
            );

            const result = await response.json();

            if (response.ok && result.success) {
                alert('✅ ' + result.message);
                window.location.reload();
            } else if (response.status === 401) {
                alert('❌ Session expired. Please log in again.');
                window.location.href = '/login';
            } else {
                alert('❌ Approval failed: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error approving as Operations Manager:', error);
            alert('❌ Error: ' + error.message);
        }
    }

    /**
     * Business Development approval
     */
    async approveAsBusinessDevelopment() {
        try {
            const comments = document.getElementById('bdComments')?.value || '';
            const formDataUpdates = this.collectFormDataUpdates();

            const response = await ApiClient.post(
                `/api/workflow/submissions/${this.submissionId}/approve-bd`,
                {
                    comments: comments,
                    form_data: formDataUpdates
                },
                false
            );

            const result = await response.json();

            if (response.ok && result.success) {
                alert('✅ ' + result.message);
                window.location.reload();
            } else if (response.status === 401) {
                alert('❌ Session expired. Please log in again.');
                window.location.href = '/login';
            } else {
                alert('❌ Approval failed: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error approving as Business Development:', error);
            alert('❌ Error: ' + error.message);
        }
    }

    /**
     * Procurement approval
     */
    async approveAsProcurement() {
        try {
            const comments = document.getElementById('procurementComments')?.value || '';
            const formDataUpdates = this.collectFormDataUpdates();

            const response = await ApiClient.post(
                `/api/workflow/submissions/${this.submissionId}/approve-procurement`,
                {
                    comments: comments,
                    form_data: formDataUpdates
                },
                false
            );

            const result = await response.json();

            if (response.ok && result.success) {
                alert('✅ ' + result.message);
                window.location.reload();
            } else if (response.status === 401) {
                alert('❌ Session expired. Please log in again.');
                window.location.href = '/login';
            } else {
                alert('❌ Approval failed: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error approving as Procurement:', error);
            alert('❌ Error: ' + error.message);
        }
    }

    /**
     * General Manager final approval
     */
    async approveAsGeneralManager() {
        try {
            const comments = document.getElementById('gmComments')?.value || '';
            const signature = this.signaturePads.gm ? this.signaturePads.gm.toDataURL() : '';

            if (this.signaturePads.gm && this.signaturePads.gm.isEmpty()) {
                alert('Please provide your signature before final approval.');
                return;
            }

            const formDataUpdates = this.collectFormDataUpdates();

            const response = await ApiClient.post(
                `/api/workflow/submissions/${this.submissionId}/approve-gm`,
                {
                    comments: comments,
                    signature: signature,
                    form_data: formDataUpdates
                },
                false
            );

            const result = await response.json();

            if (response.ok && result.success) {
                alert('✅ ' + result.message);
                window.location.reload();
            } else if (response.status === 401) {
                alert('❌ Session expired. Please log in again.');
                window.location.href = '/login';
            } else {
                alert('❌ Approval failed: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error approving as General Manager:', error);
            alert('❌ Error: ' + error.message);
        }
    }

    /**
     * Show rejection modal
     */
    showRejectionModal() {
        const modal = document.getElementById('rejectionModal');
        if (modal) {
            $(modal).modal('show');
        }
    }

    /**
     * Confirm rejection
     */
    async confirmRejection() {
        try {
            const reason = document.getElementById('rejectionReason')?.value || '';

            if (!reason.trim()) {
                alert('Please provide a reason for rejection.');
                return;
            }

            const response = await ApiClient.post(
                `/api/workflow/submissions/${this.submissionId}/reject`,
                { reason: reason },
                false
            );

            const result = await response.json();

            if (response.ok && result.success) {
                alert('✅ ' + result.message);
                $('#rejectionModal').modal('hide');
                window.location.reload();
            } else if (response.status === 401) {
                alert('❌ Session expired. Please log in again.');
                window.location.href = '/login';
            } else {
                alert('❌ Rejection failed: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error rejecting submission:', error);
            alert('❌ Error: ' + error.message);
        }
    }

    /**
     * Collect form data updates (override in specific forms)
     */
    collectFormDataUpdates() {
        // To be overridden by specific form implementations
        return {};
    }

    /**
     * Update workflow UI based on status
     */
    updateWorkflowUI(workflowStatus) {
        this.currentStatus = workflowStatus;

        const statusMap = {
            'submitted': 25,
            'operations_manager_review': 40,
            'operations_manager_approved': 50,
            'bd_procurement_review': 65,
            'general_manager_review': 80,
            'completed': 100,
            'rejected': 0
        };

        const progress = statusMap[workflowStatus] || 25;
        const progressBar = document.getElementById('workflowProgressBar');

        if (progressBar) {
            progressBar.style.width = progress + '%';
            progressBar.setAttribute('aria-valuenow', progress);
            progressBar.textContent = this.getStageText(workflowStatus);

            // Update color based on status
            progressBar.className = 'progress-bar';
            if (workflowStatus === 'completed') {
                progressBar.classList.add('bg-success');
            } else if (workflowStatus === 'rejected') {
                progressBar.classList.add('bg-danger');
            } else {
                progressBar.classList.add('bg-primary');
            }
        }

        // Show/hide sections based on workflow status and user designation
        this.showRelevantSections(workflowStatus);
    }

    /**
     * Get stage text for display
     */
    getStageText(status) {
        const stageTexts = {
            'submitted': 'Stage 1: Submitted',
            'operations_manager_review': 'Stage 2: Ops Manager Review',
            'operations_manager_approved': 'Stage 2: Approved',
            'bd_procurement_review': 'Stage 3: BD & Procurement',
            'general_manager_review': 'Stage 4: GM Review',
            'completed': 'Completed ✓',
            'rejected': 'Rejected ✗'
        };
        return stageTexts[status] || 'In Progress';
    }

    /**
     * Show/hide sections based on workflow status and user designation
     */
    showRelevantSections(workflowStatus) {
        // Hide all approval sections first
        const sections = ['opsMgrSection', 'bdSection', 'procurementSection', 'gmSection'];
        sections.forEach(sectionId => {
            const section = document.getElementById(sectionId);
            if (section) section.style.display = 'none';
        });

        // Show based on status and designation
        if (workflowStatus === 'operations_manager_review' && this.userDesignation === 'operations_manager') {
            const section = document.getElementById('opsMgrSection');
            if (section) section.style.display = 'block';
        }

        if (workflowStatus === 'bd_procurement_review') {
            if (this.userDesignation === 'business_development') {
                const section = document.getElementById('bdSection');
                if (section) section.style.display = 'block';
            }
            if (this.userDesignation === 'procurement') {
                const section = document.getElementById('procurementSection');
                if (section) section.style.display = 'block';
            }
        }

        if (workflowStatus === 'general_manager_review' && this.userDesignation === 'general_manager') {
            const section = document.getElementById('gmSection');
            if (section) section.style.display = 'block';
        }

        // Update status text
        const statusText = document.getElementById('workflowStatusText');
        if (statusText) {
            statusText.textContent = this.getStatusDescription(workflowStatus);
        }
    }

    /**
     * Get human-readable status description
     */
    getStatusDescription(status) {
        const descriptions = {
            'submitted': 'Submitted by Supervisor - Awaiting Operations Manager Review',
            'operations_manager_review': 'Under Review by Operations Manager',
            'operations_manager_approved': 'Approved by Operations Manager - Forwarded to BD & Procurement',
            'bd_procurement_review': 'Under Review by Business Development and Procurement Teams',
            'general_manager_review': 'Under Review by General Manager for Final Approval',
            'completed': 'Fully Approved - Workflow Complete',
            'rejected': 'Rejected - Requires Revision by Supervisor'
        };
        return descriptions[status] || 'Processing...';
    }

    /**
     * Initialize the workflow manager
     */
    init() {
        this.initializeSignaturePads();
        this.setupApprovalHandlers();
        console.log('✅ Workflow Manager initialized');
    }
}

// Export for use in other scripts
window.WorkflowManager = WorkflowManager;
