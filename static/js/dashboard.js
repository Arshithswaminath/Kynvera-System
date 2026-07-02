/**
 * Amaan Dashboard JavaScript
 * Extracted from inline scripts for better maintainability and caching
 */

// ===========================================
// Utility Functions
// ===========================================

// Global escapeHtml function
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Token refresh state - prevents multiple simultaneous refresh attempts
let isRefreshing = false;
let refreshPromise = null;

// Helper function to refresh access token using refresh token
async function refreshAccessToken() {
  // If already refreshing, wait for the existing refresh to complete
  if (isRefreshing && refreshPromise) {
    return refreshPromise;
  }
  
  isRefreshing = true;
  
  refreshPromise = (async () => {
    try {
      const headers = { 'Content-Type': 'application/json' };
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        headers['Authorization'] = 'Bearer ' + refreshToken;
      }
      /* If refresh_token is only in httpOnly cookie, still POST with credentials */
      const response = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: headers,
        credentials: 'include'
      });
      
      if (!response.ok) {
        if (response.status === 401 || response.status === 422) {
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          localStorage.removeItem('user');
        }
        return null;
      }
      
      const data = await response.json();
      if (data.access_token) {
        localStorage.setItem('access_token', data.access_token);
        return data.access_token;
      }
      return null;
    } catch (error) {
      return null;
    } finally {
      isRefreshing = false;
      refreshPromise = null;
    }
  })();
  
  return refreshPromise;
}

// Helper function to make authenticated fetch with automatic token refresh
async function authenticatedFetch(url, options = {}) {
  let token = localStorage.getItem('access_token');
  if (!token) {
    return { ok: false, status: 401 };
  }
  
  // Make initial request
  const response = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`
    }
  });
  
  // If 401, try to refresh token and retry once
  if (response.status === 401) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      // Retry with new token
      return fetch(url, {
        ...options,
        headers: {
          ...options.headers,
          'Authorization': `Bearer ${newToken}`
        }
      });
    } else {
      // Refresh failed, redirect to login
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
      window.location.href = '/login';
      return { ok: false, status: 401 };
    }
  }
  
  return response;
}

// ===========================================
// User & Authentication Functions
// ===========================================

// Load and display user welcome message
function loadUserWelcome() {
  try {
    const userData = localStorage.getItem('user');
    if (userData) {
      const user = JSON.parse(userData);
      const displayName = user.full_name || user.username;
      
      const welcomeText = document.getElementById('welcome-text');
      if (welcomeText) {
        welcomeText.textContent = `Welcome, ${displayName}!`;
      }
      
      checkAndShowAdminMenu(user);
      updateModuleVisibility(user);
      if (typeof loadPendingCount === 'function') {
        loadPendingCount(user);
      }
    } else {
      const token = localStorage.getItem('access_token');
      if (token) {
        fetch('/api/auth/me', {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        })
        .then(response => response.json())
        .then(data => {
          if (data.user) {
            localStorage.setItem('user', JSON.stringify(data.user));
            const displayName = data.user.full_name || data.user.username;
            const welcomeText = document.getElementById('welcome-text');
            if (welcomeText) {
              welcomeText.textContent = `Welcome, ${displayName}!`;
            }
            
            checkAndShowAdminMenu(data.user);
            updateModuleVisibility(data.user);
            if (typeof loadPendingCount === 'function') {
              loadPendingCount(data.user);
            }
          }
        })
        .catch(error => {
          console.error('Failed to fetch user:', error);
        });
      } else {
        const userStr = localStorage.getItem('user');
        if (userStr) {
          try {
            const user = JSON.parse(userStr);
            checkAndShowAdminMenu(user);
            updateModuleVisibility(user);
            if (typeof loadPendingCount === 'function') {
              loadPendingCount(user);
            }
          } catch (e) {
            console.error('Error parsing user from localStorage:', e);
          }
        }
      }
    }
  } catch (error) {
    console.error('Error loading user welcome:', error);
  }
}

function userHasBdEmailAccess(user) {
  if (!user) return false;
  if (user.role === 'admin') return true;
  if (user.designation === 'business_development') return true;
  return user.access_business_development === true;
}

function userHasInspectionNavAccess(user) {
  if (!user) return false;
  if (user.role === 'admin') return true;
  return user.access_hvac === true || user.access_civil === true || user.access_cleaning === true;
}

function userHasHrNavAccess(user) {
  if (!user) return false;
  if (user.role === 'admin') return true;
  if (user.access_hr === true) return true;
  const d = (user.designation || '').trim().toLowerCase();
  if (d === 'hr_manager' || d === 'general_manager') return true;
  return false;
}

function userHasSubmittedFormsModuleAccess(user) {
  if (!user) return false;
  if (user.role === 'admin') return true;
  // Every logged-in user can open My submitted forms for items they submitted.
  return true;
}

function userHasDocHubNavAccess(user) {
  if (!user) return false;
  if (user.role === 'admin') return true;
  if (user.can_access_dochub === false) return false;
  return true;
}

// Email Automation (formerly Report Generation / MMR) surfaced in Amaan.
// Set AMAAN_REPORT_GENERATION_ENABLED to false to hide it from the UI again.
var AMAAN_REPORT_GENERATION_ENABLED = true;
function userHasReportGenerationNavAccess(user) {
  if (!AMAAN_REPORT_GENERATION_ENABLED) return false;
  if (!user) return false;
  if (user.role === 'admin') return true;
  return user.access_report_generation === true;
}

/** Navbar items tied to admin profile module flags (main_navbar.html). */
function applyProfileBasedNavVisibility(user) {
  const inspectionEl = document.getElementById('inspection-forms-menu-item');
  if (inspectionEl) {
    inspectionEl.style.display = userHasInspectionNavAccess(user) ? 'list-item' : 'none';
  }
  const hrEl = document.getElementById('hr-forms-menu-item');
  if (hrEl) {
    hrEl.style.display = userHasHrNavAccess(user) ? 'list-item' : 'none';
  }
  const dhEl = document.getElementById('dochub-menu-item');
  if (dhEl) {
    dhEl.style.display = userHasDocHubNavAccess(user) ? 'list-item' : 'none';
  }
  const tktEl = document.getElementById('ticketing-menu-item');
  if (tktEl) {
    tktEl.style.display = (user && (user.role === 'admin' || user.access_ticketing === true)) ? 'list-item' : 'none';
  }
  const opsEl = document.getElementById('operations-menu-item');
  if (opsEl) {
    opsEl.style.display = (user && (user.role === 'admin' || user.access_operations === true)) ? 'list-item' : 'none';
  }
  const reportEl = document.getElementById('report-gen-menu-item');
  if (reportEl) {
    reportEl.style.display = userHasReportGenerationNavAccess(user) ? 'list-item' : 'none';
  }
}

// Function to check and show admin menu
function checkAndShowAdminMenu(user) {
  const adminMenuItem = document.getElementById('admin-menu-item');
  const deviceMgmtMenuItem = document.getElementById('device-management-menu-item');
  const bdModuleMenuItem = document.getElementById('bd-module-menu-item');
  const financeMenuItem = document.getElementById('finance-menu-item');
  const historyMenuItem = document.getElementById('review-history-menu-item');
  const submittedFormsMenuItem = document.getElementById('submitted-forms-menu-item');

  if (submittedFormsMenuItem) {
    const showSubmitted = userHasSubmittedFormsModuleAccess(user);
    submittedFormsMenuItem.style.display = showSubmitted ? 'list-item' : 'none';
    submittedFormsMenuItem.classList.toggle('has-submitted-dropdown', !!showSubmitted);
    if (!showSubmitted) submittedFormsMenuItem.classList.remove('open');
  }

  // Admin menu and Device Management: admin only — explicitly hide for non-admin
  if (adminMenuItem) {
    adminMenuItem.style.display = (user && user.role === 'admin') ? 'list-item' : 'none';
  }
  if (deviceMgmtMenuItem) {
    deviceMgmtMenuItem.style.display = (user && user.role === 'admin') ? 'list-item' : 'none';
  }
  if (bdModuleMenuItem) {
    bdModuleMenuItem.style.display = (user && user.role === 'admin') ? 'list-item' : 'none';
  }

  // Finance & Invoicing: admin, GM, OM, or ticketing access
  if (financeMenuItem) {
    const showFinance = user && (
      user.role === 'admin' ||
      (user.designation && ['general_manager', 'operations_manager'].includes(user.designation)) ||
      user.access_ticketing === true
    );
    financeMenuItem.style.display = showFinance ? 'list-item' : 'none';
  }

  // Legacy Review History nav is retired in favor of unified Submitted Forms.
  if (historyMenuItem) {
    historyMenuItem.style.display = 'none';
  }

  applyProfileBasedNavVisibility(user);
  
  if (user && !user.role) {
    const token = localStorage.getItem('access_token');
    if (token) {
      fetch('/api/auth/me', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      .then(response => response.json())
      .then(data => {
        if (data.user) {
          localStorage.setItem('user', JSON.stringify(data.user));
          checkAndShowAdminMenu(data.user);
          updateModuleVisibility(data.user);
          if (typeof loadPendingCount === 'function') {
            loadPendingCount(data.user);
          }
        }
      })
      .catch(error => {
        console.error('Failed to fetch user role:', error);
      });
    }
  }
}

// ===========================================
// Module Visibility Functions
// ===========================================

let _dashboardModuleEntranceTimer = null;

function _dashboardPrefersReducedMotion() {
  try {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch (e) {
    return false;
  }
}

function scheduleDashboardModuleEntrance() {
  if (!document.body.classList.contains('page-dashboard')) return;
  const grid = document.getElementById('modulesGrid');
  if (!grid) return;
  clearTimeout(_dashboardModuleEntranceTimer);
  _dashboardModuleEntranceTimer = setTimeout(function() {
    _dashboardModuleEntranceTimer = null;
    playDashboardModuleEntrance();
  }, 50);
}

function playDashboardModuleEntrance() {
  const grid = document.getElementById('modulesGrid');
  if (!grid || !document.body.classList.contains('page-dashboard')) return;

  if (window.innerWidth <= 768) {
    grid.classList.remove('modules-grid--boot');
    grid.classList.remove('modules-grid--entrance-active');
    Array.from(grid.querySelectorAll(':scope > .module-card')).forEach(function(card) {
      card.style.removeProperty('--dd-stagger');
    });
    return;
  }

  const cards = Array.from(grid.querySelectorAll(':scope > .module-card'));
  const visible = cards.filter(function(card) {
    return !/display\s*:\s*none/i.test(card.getAttribute('style') || '');
  });

  cards.forEach(function(card) {
    card.style.removeProperty('--dd-stagger');
  });
  grid.classList.remove('modules-grid--entrance-active');

  if (_dashboardPrefersReducedMotion()) {
    grid.classList.remove('modules-grid--boot');
    return;
  }

  if (!visible.length) {
    grid.classList.remove('modules-grid--boot');
    return;
  }

  requestAnimationFrame(function() {
    requestAnimationFrame(function() {
      visible.forEach(function(card, i) {
        card.style.setProperty('--dd-stagger', (72 + i * 46) + 'ms');
      });
      grid.classList.remove('modules-grid--boot');
      grid.classList.add('modules-grid--entrance-active');
    });
  });
}

function updateModuleVisibility(user) {
  if (!user) return;

  const isAdmin = user.role === 'admin';

  // Helper: if admin, always show; otherwise check specific access
  const shouldShowModule = (specificCheck) => isAdmin || specificCheck;

  // Check Inspection Form access (HVAC, Civil, or Cleaning)
  const inspectionCard = document.getElementById('module-inspection');
  if (inspectionCard) {
    const hasInspectionAccess = shouldShowModule(user.access_hvac === true || user.access_civil === true || user.access_cleaning === true);
    inspectionCard.style.display = hasInspectionAccess ? 'block' : 'none';
    inspectionCard.style.visibility = hasInspectionAccess ? 'visible' : 'hidden';
  }
  
  const submittedFormsCard = document.getElementById('module-submitted-forms');
  const submittedFormsMenuItem = document.getElementById('submitted-forms-menu-item');
  const showSubmittedFormsMod = shouldShowModule(userHasSubmittedFormsModuleAccess(user));
  if (submittedFormsCard) {
    submittedFormsCard.style.display = showSubmittedFormsMod ? 'block' : 'none';
    submittedFormsCard.style.visibility = showSubmittedFormsMod ? 'visible' : 'hidden';
  }
  if (submittedFormsMenuItem) {
    submittedFormsMenuItem.style.display = showSubmittedFormsMod ? 'list-item' : 'none';
  }

  // Legacy Review History card is retired in favor of unified Submitted Forms.
  const reviewHistoryCard = document.getElementById('module-review-history');
  if (reviewHistoryCard) {
    reviewHistoryCard.style.display = 'none';
    reviewHistoryCard.style.visibility = 'hidden';
  }

  // Check BD Email Module access (BD designation, module flag, or admin via userHasBdEmailAccess)
  const bdEmailCard = document.getElementById('module-bd-email');
  if (bdEmailCard) {
    const showBdEmail = shouldShowModule(userHasBdEmailAccess(user));
    bdEmailCard.style.display = showBdEmail ? 'block' : 'none';
    bdEmailCard.style.visibility = showBdEmail ? 'visible' : 'hidden';
  }

  // Check Device Management access (admin only)
  const deviceMgmtCard = document.getElementById('module-device-management');
  if (deviceMgmtCard) {
    deviceMgmtCard.style.display = isAdmin ? 'block' : 'none';
    deviceMgmtCard.style.visibility = isAdmin ? 'visible' : 'hidden';
  }

  // Check Business Development module access (admin always sees it)
  const bdCard = document.getElementById('module-bd');
  if (bdCard) {
    bdCard.style.display = isAdmin ? 'block' : 'none';
    bdCard.style.visibility = isAdmin ? 'visible' : 'hidden';
  }

  // HR Module: match admin "HR module" flag and HR/GM designations (see /hr/ hub routing)
  const hrCard = document.getElementById('module-hr');
  if (hrCard) {
    const showHr = shouldShowModule(userHasHrNavAccess(user));
    hrCard.style.display = showHr ? 'block' : 'none';
    hrCard.style.visibility = showHr ? 'visible' : 'hidden';
  }

  // Check Procurement Module access
  const procurementCard = document.getElementById('module-procurement');
  const procurementMenuItem = document.getElementById('procurement-menu-item');
  const hasProcurementAccess = shouldShowModule(user.access_procurement_module === true);
  if (procurementCard) {
    procurementCard.style.display = hasProcurementAccess ? 'block' : 'none';
    procurementCard.style.visibility = hasProcurementAccess ? 'visible' : 'hidden';
  }
  if (procurementMenuItem) {
    procurementMenuItem.style.display = hasProcurementAccess ? 'list-item' : 'none';
  }

  // Service tickets
  const ticketingCard = document.getElementById('module-ticketing');
  if (ticketingCard) {
    const showTicketing = shouldShowModule(user.access_ticketing === true);
    ticketingCard.style.display = showTicketing ? 'block' : 'none';
    ticketingCard.style.visibility = showTicketing ? 'visible' : 'hidden';
  }

  // Operations (Over Time + Trading Invoices)
  const operationsCard = document.getElementById('module-operations');
  if (operationsCard) {
    const showOperations = shouldShowModule(user.access_operations === true);
    operationsCard.style.display = showOperations ? 'block' : 'none';
    operationsCard.style.visibility = showOperations ? 'visible' : 'hidden';
  }

  // Check Report Generation / MMR hub
  const reportGenCard = document.getElementById('module-report-generation');
  if (reportGenCard) {
    const showReport = shouldShowModule(userHasReportGenerationNavAccess(user));
    reportGenCard.style.display = showReport ? 'block' : 'none';
    reportGenCard.style.visibility = showReport ? 'visible' : 'hidden';
  }

  // Finance & Invoicing (Amaan-specific) — admin, GM, or OM
  const financeCard = document.getElementById('module-finance');
  if (financeCard) {
    const showFinance = shouldShowModule(
      (user.designation && ['general_manager', 'operations_manager'].includes(user.designation)) ||
      user.access_ticketing === true
    );
    financeCard.style.display = showFinance ? 'block' : 'none';
    financeCard.style.visibility = showFinance ? 'visible' : 'hidden';
  }

  // Civil Defense Notifications (Amaan-specific) — admin, BD, or inspection access
  const cdNotifCard = document.getElementById('module-cd-notifications');
  if (cdNotifCard) {
    const showCdNotif = shouldShowModule(
      user.access_business_development === true ||
      user.access_hvac === true ||
      user.access_civil === true ||
      user.access_cleaning === true ||
      (user.designation && ['business_development', 'operations_manager', 'general_manager'].includes(user.designation))
    );
    cdNotifCard.style.display = showCdNotif ? 'block' : 'none';
    cdNotifCard.style.visibility = showCdNotif ? 'visible' : 'hidden';
  }
  
  const modulesGrid = document.getElementById('modulesGrid');
  const modulesSection = document.getElementById('modules');
  if (modulesSection) {
    const visibleCount = modulesGrid
      ? Array.from(modulesGrid.children).filter(function (card) {
          const style = card.getAttribute('style') || '';
          return card.classList.contains('module-card')
            && !/display\s*:\s*none/i.test(style)
            && card.style.visibility !== 'hidden';
        }).length
      : 0;
    const existingMsg = modulesSection.querySelector('.no-access-message');
    if (visibleCount === 0 && !isAdmin) {
      if (!existingMsg) {
        const noAccessMsg = document.createElement('div');
        noAccessMsg.className = 'no-access-message';
        noAccessMsg.style.cssText = 'text-align: center; padding: 3rem; color: var(--text-light);';
        noAccessMsg.innerHTML = `
        <h3 style="margin-bottom: 1rem; color: var(--text-dark);">No Module Access</h3>
        <p>You don't have access to any modules yet. Please contact an administrator to grant access.</p>
      `;
        modulesSection.appendChild(noAccessMsg);
      }
    } else if (existingMsg) {
      existingMsg.remove();
    }
  }

  updateModuleGridLayout();

  if (document.body.classList.contains('page-dashboard') && document.getElementById('modulesGrid')) {
    scheduleDashboardModuleEntrance();
  }

  applyProfileBasedNavVisibility(user);
}

function getVisibleModuleCards(modulesGrid) {
  if (!modulesGrid) return [];
  return Array.from(modulesGrid.children).filter(function (card) {
    const style = card.getAttribute('style') || '';
    return card.classList.contains('module-card')
      && !/display\s*:\s*none/i.test(style)
      && card.style.visibility !== 'hidden';
  });
}

/** Grid columns are controlled by CSS — this just clears any stale inline overrides. */
function updateModuleGridLayout() {
  const modulesGrid = document.getElementById('modulesGrid');
  if (!modulesGrid) return;
  modulesGrid.style.removeProperty('grid-template-columns');
  modulesGrid.style.removeProperty('max-width');
  modulesGrid.style.removeProperty('margin');
}

// ===========================================
// Workflow Functions
// ===========================================

// Flag to prevent duplicate calls
let submittedFormsLoading = false;

// Load submitted forms count for supervisors
async function loadSubmittedFormsCount(user) {
  if (!user || user.designation !== 'supervisor') return;
  
  // Prevent duplicate simultaneous calls
  if (submittedFormsLoading) return;
  submittedFormsLoading = true;
  
  try {
    const response = await authenticatedFetch('/api/workflow/submissions/my-submissions');
    
    if (!response || !response.ok) return;
    
    const data = await response.json();
    const submissions = data.submissions || [];
    
    // Update module card badge
    const badge = document.getElementById('submittedFormsCount');
    if (badge) {
      if (submissions.length > 0) {
        badge.textContent = submissions.length > 99 ? '99+' : submissions.length;
        badge.style.display = 'inline-block';
      } else {
        badge.style.display = 'none';
      }
    }
    
    // Update navigation badge
    const navBadge = document.getElementById('navSubmittedBadge');
    if (navBadge) {
      if (submissions.length > 0) {
        navBadge.textContent = submissions.length > 99 ? '99+' : submissions.length;
        navBadge.style.display = 'inline';
      } else {
        navBadge.style.display = 'none';
      }
    }
    
  } catch (error) {
    console.error('Error loading submitted forms count:', error);
  } finally {
    submittedFormsLoading = false;
  }
}

// Load pending count and show pending review module card
async function loadPendingCount(user) {
  const pendingModule = document.getElementById('module-pending-review');
  const reviewHistoryModule = document.getElementById('module-review-history');
  const moduleBadge = document.getElementById('modulePendingBadge');
  if (reviewHistoryModule) {
    reviewHistoryModule.style.display = 'none';
    reviewHistoryModule.style.visibility = 'hidden';
  }
  
  if (user && user.role === 'admin') {
    if (pendingModule) {
      pendingModule.style.display = 'none';
      pendingModule.style.visibility = 'hidden';
    }
    updateMobileMenuHint(0);
    return;
  }
  
  const reviewerDesignations = ['operations_manager', 'business_development', 'procurement', 'general_manager'];
  const isReviewer = user && ((user.designation && reviewerDesignations.includes(user.designation)) || user.access_business_development === true);
  const isSupervisor = user && user.designation === 'supervisor';
  const pendingReviewMenuItem = document.getElementById('pending-review-menu-item');

  // Anyone who can review forms (supervisor, OM, BD, procurement, GM) gets the Pending Review link
  const canReview = isReviewer || isSupervisor;

  // Non-reviewers (plain technicians / employees): hide both module cards
  if (!canReview) {
    if (pendingModule) {
      pendingModule.style.display = 'none';
      pendingModule.style.visibility = 'hidden';
    }
    if (reviewHistoryModule) {
      reviewHistoryModule.style.display = 'none';
      reviewHistoryModule.style.visibility = 'hidden';
    }
    if (pendingReviewMenuItem) {
      pendingReviewMenuItem.style.display = 'none';
    }
    updateMobileMenuHint(0);
    return;
  }

  // Reviewers / supervisors: show the Pending Review menu item
  if (pendingReviewMenuItem) {
    pendingReviewMenuItem.style.display = 'list-item';
  }
  
  try {
    const response = await authenticatedFetch('/api/workflow/submissions/pending');
    
    if (!response || !response.ok) {
      return;
    }
    
    const data = await response.json();
    const submissions = data.submissions || [];
    
    if (pendingModule) {
      pendingModule.style.display = 'block';
      pendingModule.style.visibility = 'visible';
    }
    
    const navBadge = document.getElementById('navPendingBadge');
    if (navBadge) {
      if (submissions.length > 0) {
        navBadge.textContent = submissions.length;
        navBadge.style.display = 'inline-block';
      } else {
        navBadge.style.display = 'none';
      }
    }
    
    if (moduleBadge) {
      if (submissions.length > 0) {
        moduleBadge.textContent = submissions.length;
        moduleBadge.style.display = 'inline-block';
      } else {
        moduleBadge.style.display = 'none';
      }
    }

    updateMobileMenuHint(submissions.length);
    
    updateModuleGridLayout();
    
  } catch (error) {
    console.error('Error loading pending count:', error);
  }
}

// Helper function to get workflow action text
function getWorkflowAction(designation) {
  const actionMap = {
    'operations_manager': 'Operations Manager Review',
    'business_development': 'Business Development Review',
    'procurement': 'Procurement Review',
    'general_manager': 'General Manager Approval'
  };
  return actionMap[designation] || 'Your Review';
}

// Open submission for supervisor review
window.openSubmissionForReview = async function(submissionId, moduleUrl) {
  try {
    const token = localStorage.getItem('access_token');
    
    await fetch(`/api/workflow/submissions/${submissionId}/start-review`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    });
    
    window.location.href = `/${moduleUrl}/form?edit=${submissionId}&review=true`;
  } catch (error) {
    console.error('Error starting review:', error);
    alert('Failed to start review. Please try again.');
  }
};

// ===========================================
// Profile Modal Functions
// ===========================================

window.openProfileModal = function() {
  const modal = document.getElementById('profileModal');
  if (modal) {
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
    loadProfileData();
  }
};

window.closeProfileModal = function() {
  const modal = document.getElementById('profileModal');
  if (modal) {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  }
};

function loadProfileData() {
  const profileContent = document.getElementById('profileContent');
  const token = localStorage.getItem('access_token');
  const cachedUser = localStorage.getItem('user');
  
  if (!token) {
    if (cachedUser) {
      try {
        const user = JSON.parse(cachedUser);
        displayProfileData(user);
        checkAndShowAdminMenu(user);
        updateModuleVisibility(user);
        return;
      } catch (e) {
        console.warn('Failed to parse cached user data');
      }
    }
    profileContent.innerHTML = '<div style="text-align: center; padding: 2rem;"><p style="color: var(--text-light);">Please log in to view your profile.</p></div>';
    return;
  }

  profileContent.innerHTML = '<div style="text-align: center; padding: 2rem;"><div class="spinner" style="border: 4px solid rgba(210, 23, 37, 0.1); border-top: 4px solid var(--primary); border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto;"></div><p style="margin-top: 1rem; color: var(--text-light);">Loading profile...</p></div>';

  fetch('/api/auth/me', {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  })
  .then(response => {
    if (!response.ok) {
      if (response.status === 401 && cachedUser) {
        try {
          const user = JSON.parse(cachedUser);
          console.log('Using cached user data due to 401');
          displayProfileData(user);
          checkAndShowAdminMenu(user);
          updateModuleVisibility(user);
          return null;
        } catch (e) {
          console.warn('Failed to parse cached user data');
        }
      }
      throw new Error('Failed to fetch profile');
    }
    return response.json();
  })
  .then(data => {
    if (data === null) return;
    if (data && data.user) {
      localStorage.setItem('user', JSON.stringify(data.user));
      displayProfileData(data.user);
      checkAndShowAdminMenu(data.user);
      updateModuleVisibility(data.user);
      if (typeof loadPendingCount === 'function') {
        loadPendingCount(data.user);
      }
    } else {
      throw new Error('No user data received');
    }
  })
  .catch(error => {
    console.error('Error loading profile:', error);
    if (cachedUser) {
      try {
        const user = JSON.parse(cachedUser);
        console.log('Using cached user data as fallback');
        displayProfileData(user);
        checkAndShowAdminMenu(user);
        updateModuleVisibility(user);
        return;
      } catch (e) {
        console.warn('Failed to parse cached user data');
      }
    }
    profileContent.innerHTML = `<div style="text-align: center; padding: 2rem;"><p style="color: #dc3545;">Error loading profile. Please try again or re-login.</p><button class="btn btn-primary btn-sm mt-2" onclick="window.location.href='/login'">Login</button></div>`;
  });
}

function displayProfileData(user) {
  const profileContent = document.getElementById('profileContent');
  
  const formatDate = (dateStr) => {
    if (!dateStr) return 'Never';
    try {
      let utcDateString = dateStr;
      if (!utcDateString.endsWith('Z') && !utcDateString.includes('+') && !utcDateString.includes('-', 10)) {
        utcDateString = utcDateString + 'Z';
      }
      const date = new Date(utcDateString);
      return date.toLocaleString('en-US', { 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        timeZone: 'Asia/Dubai'
      }) + ' (GST)';
    } catch {
      return dateStr;
    }
  };

  const getModuleAccess = () => {
    const modules = [];
    if (user.role === 'admin' || user.access_hvac) modules.push('HVAC & MEP');
    if (user.role === 'admin' || user.access_civil) modules.push('Civil Works');
    if (user.role === 'admin' || user.access_cleaning) modules.push('Cleaning');
    if (userHasHrNavAccess(user)) modules.push('HR');
    if (user.role === 'admin' || user.access_procurement_module) modules.push('Procurement');
    if (user.role === 'admin' || user.designation === 'business_development' || user.access_business_development) modules.push('Business Development');
    if (userHasReportGenerationNavAccess(user)) modules.push('Report Generation');
    return modules.length > 0 ? modules.join(', ') : 'None';
  };

  const getRoleDisplay = () => {
    const roleMap = {
      'admin': 'Administrator',
      'inspector': 'Inspector',
      'user': 'User'
    };
    return roleMap[user.role] || user.role;
  };

  const getDesignationDisplay = () => {
    if (!user.designation) return 'Not assigned';
    const designationMap = {
      'supervisor': 'Supervisor',
      'operations_manager': 'Operations Manager',
      'business_development': 'Business Development',
      'procurement': 'Procurement',
      'general_manager': 'General Manager',
      'hr_manager': 'HR Manager',
      'employee': 'Employee',
      'admin': 'Admin'
    };
    return designationMap[user.designation] || user.designation;
  };

  const getInitials = () => {
    if (user.full_name) {
      return user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
    }
    return user.username ? user.username.slice(0, 2).toUpperCase() : 'U';
  };

  const html = getProfileCardHTML(user, getInitials, getDesignationDisplay, getRoleDisplay, getModuleAccess, formatDate);
  profileContent.innerHTML = html;
  initProfileSignatureDefaults(user);
  initManagedProfileFields();
}

function getProfileCardHTML(user, getInitials, getDesignationDisplay, getRoleDisplay, getModuleAccess, formatDate) {
  const modules = [];
  if (user.role === 'admin' || user.access_hvac) modules.push({ name: 'HVAC & MEP', color: '#3b82f6' });
  if (user.role === 'admin' || user.access_civil) modules.push({ name: 'Civil Works', color: '#8b5cf6' });
  if (user.role === 'admin' || user.access_cleaning) modules.push({ name: 'Cleaning', color: '#10b981' });
  if (userHasHrNavAccess(user)) modules.push({ name: 'HR', color: '#f59e0b' });
  if (user.role === 'admin' || user.access_procurement_module) modules.push({ name: 'Procurement', color: '#7c3aed' });
  if (user.role === 'admin' || user.designation === 'business_development' || user.access_business_development) modules.push({ name: 'Business Development', color: '#0d9488' });
  if (userHasReportGenerationNavAccess(user)) modules.push({ name: 'Report Generation', color: '#0369a1' });
  
  const moduleBadges = modules.length > 0 
    ? modules.map(m => `<span class="pro-module-badge" style="--badge-color: ${m.color}">${m.name}</span>`).join('')
    : '<span class="pro-no-access">No modules assigned</span>';

  const hrJobTitle = escapeHtml(user.job_designation || '—');
  const annualLeavesDisp = user.annual_leave_days != null ? escapeHtml(String(user.annual_leave_days)) : '—';
  const otherLeavesDisp = user.other_leave_days != null ? escapeHtml(String(user.other_leave_days)) : '—';
  const rm = user.reporting_manager;
  const reportingMgrDisp = rm
    ? `${escapeHtml(rm.full_name || rm.username || '')}${rm.email ? `<span style="display:block;font-size:0.8rem;color:#64748b;margin-top:2px;">${escapeHtml(rm.email)}</span>` : ''}`
    : '—';

  return `
    <style>
      /* Modern Profile Modal Styles - Enhanced */
      .pro-container {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        width: 100%;
        max-width: 100%;
        padding: 0;
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        flex: 1;
        min-height: 0;
        overflow: hidden;
      }
      
      /* Hero Section — fixed strip at top, left-aligned row */
      .pro-hero {
        position: relative;
        flex-shrink: 0;
        padding: 0.85rem 3.5rem 1rem 1.25rem;
        background: linear-gradient(135deg, #7a0d15 0%, #b01320 50%, #d21725 100%);
        border-radius: 0;
        margin: 0;
        overflow: hidden;
      }
      
      .pro-hero::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0; bottom: 0;
        background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.03'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
        opacity: 0.5;
      }
      
      .pro-hero-content {
        position: relative;
        z-index: 1;
        display: flex;
        flex-direction: row;
        align-items: center;
        justify-content: flex-start;
        text-align: left;
        gap: 0;
      }
      
      .pro-hero-main {
        display: flex;
        flex-direction: row;
        align-items: center;
        gap: 0.85rem;
        min-width: 0;
        flex: 1;
      }
      
      .pro-hero-text {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        justify-content: center;
        gap: 0.35rem;
        min-width: 0;
        flex: 1;
      }
      
      .pro-avatar {
        width: 64px;
        height: 64px;
        border-radius: 50%;
        background: rgba(255,255,255,0.15);
        backdrop-filter: blur(10px);
        border: 3px solid rgba(255,255,255,0.3);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.35rem;
        font-weight: 700;
        color: white;
        margin-bottom: 0;
        box-shadow: 0 8px 32px rgba(0,0,0,0.2);
        position: relative;
        flex-shrink: 0;
      }
      
      .pro-avatar::after {
        content: '';
        position: absolute;
        bottom: 2px;
        right: 2px;
        width: 14px;
        height: 14px;
        background: ${user.is_active ? '#22c55e' : '#ef4444'};
        border: 2px solid white;
        border-radius: 50%;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
      }
      
      .pro-name {
        font-size: 1.15rem;
        font-weight: 700;
        color: white;
        margin: 0;
        letter-spacing: -0.03em;
        line-height: 1.2;
        text-align: left;
        align-self: stretch;
        word-break: break-word;
      }
      
      .pro-role-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: rgba(255,255,255,0.15);
        backdrop-filter: blur(10px);
        padding: 0.35rem 0.75rem;
        border-radius: 100px;
        font-size: 0.72rem;
        font-weight: 500;
        color: rgba(255,255,255,0.95);
        border: 1px solid rgba(255,255,255,0.2);
        max-width: 100%;
        flex-wrap: wrap;
        justify-content: flex-start;
        text-align: left;
        line-height: 1.3;
      }
      
      .pro-role-badge svg {
        width: 13px;
        height: 13px;
        opacity: 0.8;
      }
      
      /* Tabs — fixed under hero */
      .pro-tabs {
        display: flex;
        gap: 0.375rem;
        padding: 0.65rem 1rem;
        background: #f8fafc;
        border-bottom: 1px solid #e2e8f0;
        margin: 0;
        flex-shrink: 0;
      }
      
      /* Only tab bodies scroll */
      .pro-tab-panels {
        flex: 1;
        min-height: 0;
        overflow-x: hidden;
        overflow-y: auto;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: none;
        -ms-overflow-style: none;
        padding: 0 1.25rem calc(1rem + env(safe-area-inset-bottom, 0px));
        box-sizing: border-box;
      }
      
      .pro-tab-panels::-webkit-scrollbar {
        width: 0;
        height: 0;
        background: transparent;
      }
      
      .pro-tab {
        flex: 1;
        padding: 0.6rem 0.75rem;
        border: none;
        background: transparent;
        font-size: 0.8rem;
        font-weight: 600;
        color: #64748b;
        cursor: pointer;
        border-radius: 8px;
        transition: all 0.2s ease;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.35rem;
      }
      
      .pro-tab:hover {
        background: #e2e8f0;
        color: #334155;
      }
      
      .pro-tab.active {
        background: white;
        color: #d21725;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
      }
      
      .pro-tab svg {
        width: 14px;
        height: 14px;
      }
      
      /* Tab Content */
      .pro-tab-content {
        display: none;
        padding: 0.55rem 0 0.5rem;
        animation: fadeIn 0.3s ease;
      }
      
      .pro-tab-content.active {
        display: block;
      }
      
      @keyframes fadeIn {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
      }
      
      /* Info List — two columns on wide profile sheet */
      .pro-info-list {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.65rem;
      }
      
      .pro-info-item {
        position: relative;
        display: flex;
        align-items: center;
        padding: 0.7rem 0.9rem;
        background: #fff;
        border-radius: 12px;
        border: 1px solid #eef1f5;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
      }

      .pro-info-item:hover {
        border-color: #dbe1ea;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.07);
        transform: translateY(-1px);
      }

      .pro-info-item--span {
        grid-column: 1 / -1;
      }

      .pro-info-content {
        flex: 1;
        min-width: 0;
      }

      .pro-info-label {
        font-size: 0.68rem;
        font-weight: 600;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        margin-bottom: 0.2rem;
      }

      .pro-info-value {
        font-size: 0.95rem;
        font-weight: 600;
        color: #1e293b;
        word-break: break-word;
        line-height: 1.3;
      }
      
      .pro-profile-edit-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.65rem;
      }
      
      @media (max-width: 540px) {
        .pro-info-list {
          grid-template-columns: 1fr;
        }
        .pro-profile-edit-grid {
          grid-template-columns: 1fr;
        }
      }
      
      /* Module Badges */
      .pro-modules-wrap {
        margin-top: 1rem;
        padding: 0.875rem;
        background: #f8fafc;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
      }
      
      .pro-modules-title {
        font-size: 0.7rem;
        font-weight: 600;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 0.625rem;
      }
      
      .pro-modules-list {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
      }
      
      .pro-module-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        padding: 0.45rem 0.75rem;
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 100px;
        font-size: 0.8rem;
        font-weight: 500;
        color: #334155;
        transition: all 0.2s ease;
      }
      
      .pro-module-badge:hover {
        border-color: var(--badge-color, #d21725);
        background: color-mix(in srgb, var(--badge-color, #d21725) 8%, white);
      }
      
      .pro-no-access {
        color: #94a3b8;
        font-size: 0.8rem;
        font-style: italic;
      }
      
      /* Footer / Member Since */
      .pro-footer, .pro-member-since {
        text-align: center;
        padding: 0.875rem 0 0.5rem;
        margin-top: 0.875rem;
        font-size: 0.8rem;
        color: #94a3b8;
        border-top: 1px solid #e2e8f0;
      }
      
      .pro-member-since strong {
        color: #64748b;
      }
      
      .pro-footer-text {
        font-size: 0.8rem;
        color: #94a3b8;
      }
      
      /* Security Section */
      .pro-security-card {
        padding: 0.875rem;
        border-radius: 10px;
        border: 1px solid;
        margin-bottom: 0.625rem;
        display: flex;
        align-items: center;
        gap: 0.875rem;
      }
      
      .pro-security-card.success {
        background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
        border-color: #86efac;
      }
      
      .pro-security-card.warning {
        background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
        border-color: #fcd34d;
      }
      
      .pro-security-icon {
        width: 38px;
        height: 38px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.1rem;
        flex-shrink: 0;
      }
      
      .pro-security-card.success .pro-security-icon {
        background: #22c55e;
        color: white;
      }
      
      .pro-security-card.warning .pro-security-icon {
        background: #f59e0b;
        color: white;
      }
      
      .pro-security-content {
        flex: 1;
        min-width: 0;
      }
      
      .pro-security-title {
        font-size: 0.875rem;
        font-weight: 600;
        color: #1e293b;
        margin-bottom: 0.125rem;
      }
      
      .pro-security-desc {
        font-size: 0.75rem;
        color: #64748b;
      }
      
      .pro-security-action {
        flex-shrink: 0;
      }
      
      .pro-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.375rem;
        padding: 0.5rem 1rem;
        font-size: 0.8rem;
        font-weight: 600;
        border-radius: 8px;
        border: none;
        cursor: pointer;
        transition: all 0.2s ease;
      }
      
      .pro-btn-primary {
        background: linear-gradient(135deg, #d21725 0%, #e8323f 100%);
        color: white;
        box-shadow: 0 2px 8px rgba(210,23,37,0.25);
      }
      
      .pro-btn-primary:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(210,23,37,0.35);
      }
      
      .pro-btn-outline {
        background: white;
        color: #d21725;
        border: 1.5px solid #d21725;
      }
      
      .pro-btn-outline:hover {
        background: #f0fdf4;
      }
      
      .pro-btn-sm {
        padding: 0.375rem 0.75rem;
        font-size: 0.75rem;
      }
      
      .pro-btn-danger {
        background: white;
        color: #dc2626;
        border: 1.5px solid #fecaca;
      }
      
      .pro-btn-danger:hover {
        background: #fef2f2;
        border-color: #dc2626;
      }
      
      .pro-btn-success {
        background: linear-gradient(135deg, #16a34a 0%, #22c55e 100%);
        color: white;
        box-shadow: 0 2px 8px rgba(22,163,74,0.25);
      }
      
      .pro-btn-success:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(22,163,74,0.35);
      }
      
      /* Signature Section */
      .pro-sig-section {
        background: #f8fafc;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
        overflow: hidden;
      }
      
      .pro-sig-header {
        padding: 0.875rem;
        border-bottom: 1px solid #e2e8f0;
        display: flex;
        align-items: center;
        gap: 0.625rem;
      }
      
      .pro-sig-header-icon {
        width: 32px;
        height: 32px;
        background: linear-gradient(135deg, #d21725 0%, #e8323f 100%);
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 0.9rem;
      }
      
      .pro-sig-header-text h4 {
        margin: 0;
        font-size: 0.875rem;
        font-weight: 600;
        color: #1e293b;
      }
      
      .pro-sig-header-text p {
        margin: 0;
        font-size: 0.7rem;
        color: #64748b;
      }
      
      .pro-sig-body {
        padding: 0.875rem;
      }
      
      .pro-sig-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0.75rem;
      }
      
      /* Mobile Responsive - Profile Modal (phones) */
      @media (max-width: 480px) {
        .pro-sig-grid {
          grid-template-columns: 1fr;
        }
        
        .pro-tab-panels {
          padding: 0 0.875rem calc(1rem + env(safe-area-inset-bottom, 0px));
          box-sizing: border-box;
        }
        
        .pro-hero {
          margin: 0;
          padding: 0.85rem 3.25rem 0.95rem 0.75rem;
        }
        
        .pro-hero-main {
          gap: 0.65rem;
        }
        
        .pro-avatar {
          width: 56px;
          height: 56px;
          font-size: 1.2rem;
        }
        
        .pro-avatar::after {
          width: 12px;
          height: 12px;
        }
        
        .pro-name {
          font-size: 1rem;
          line-height: 1.25;
          max-width: 100%;
          padding: 0;
        }
        
        .pro-role-badge {
          font-size: 0.65rem;
          padding: 0.3rem 0.6rem;
          max-width: 100%;
          flex-wrap: wrap;
          justify-content: flex-start;
          text-align: left;
          line-height: 1.35;
        }
        
        .pro-tabs {
          margin: 0;
          padding: 0.55rem 0.45rem;
          gap: 0.35rem;
          width: 100%;
          max-width: none;
          box-sizing: border-box;
          justify-content: stretch;
        }
        
        .pro-tab {
          flex: 1;
          min-width: 0;
          min-height: 44px;
          padding: 0.45rem 0.35rem;
          font-size: 0.7rem;
          gap: 0.3rem;
          border-radius: 10px;
          -webkit-tap-highlight-color: rgba(210, 23, 37, 0.12);
        }
        
        .pro-tab svg {
          width: 20px;
          height: 20px;
          flex-shrink: 0;
        }
        
        .pro-tab span {
          display: none;
        }
        
        .pro-tab-content {
          padding: 0.65rem 0 0;
        }
        
        .pro-info-list {
          gap: 0.5rem;
          grid-template-columns: 1fr;
        }
        
        .pro-info-item {
          align-items: center;
          padding: 0.6rem 0.7rem;
        }

        .pro-info-label {
          font-size: 0.625rem;
        }
        
        .pro-info-value {
          font-size: 0.875rem;
          line-height: 1.35;
        }
        
        .pro-modules-wrap {
          padding: 0.625rem 0.625rem;
          margin-top: 0.75rem;
        }
        
        .pro-modules-title {
          font-size: 0.625rem;
          margin-bottom: 0.5rem;
        }
        
        .pro-modules-list {
          display: grid;
          grid-template-columns: 1fr;
          gap: 0.45rem;
        }
        
        .pro-module-badge {
          width: 100%;
          max-width: 100%;
          box-sizing: border-box;
          justify-content: flex-start;
          padding: 0.5rem 0.7rem;
          font-size: 0.8125rem;
        }
        
        .pro-security-card {
          flex-direction: column;
          text-align: center;
          gap: 0.75rem;
          padding: 0.75rem 0.625rem;
        }
        
        .pro-security-icon {
          width: 32px;
          height: 32px;
          font-size: 0.95rem;
        }
        
        .pro-security-title {
          font-size: 0.8rem;
        }
        
        .pro-security-desc {
          font-size: 0.7rem;
        }
        
        .pro-security-action {
          width: 100%;
        }
        
        .pro-security-action .pro-btn {
          width: 100%;
        }
        
        .pro-btn {
          padding: 0.45rem 0.85rem;
          font-size: 0.7rem;
        }
        
        .pro-sig-header {
          padding: 0.625rem;
        }
        
        .pro-sig-body {
          padding: 0.625rem;
        }
        
        .pro-sig-preview {
          min-height: 70px;
        }
        
        .pro-sig-comment {
          min-height: 70px;
          padding: 0.625rem;
          font-size: 0.8rem;
        }
        
        .pro-member-since {
          font-size: 0.8125rem;
          padding: 1rem 0 0.35rem;
          margin-top: 0.35rem;
          line-height: 1.45;
        }
      }
      
      .pro-sig-preview {
        background: white;
        border: 2px dashed #cbd5e1;
        border-radius: 10px;
        min-height: 80px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.2s ease;
        position: relative;
        overflow: hidden;
      }
      
      .pro-sig-preview:hover {
        border-color: #d21725;
        background: #f0fdf4;
      }
      
      .pro-sig-preview.has-sig {
        border-style: solid;
        border-color: #22c55e;
      }
      
      .pro-sig-preview img {
        max-width: 90%;
        max-height: 70px;
        object-fit: contain;
      }
      
      .pro-sig-empty {
        text-align: center;
        color: #94a3b8;
      }
      
      .pro-sig-empty-icon {
        font-size: 1.5rem;
        margin-bottom: 0.375rem;
        opacity: 0.5;
      }
      
      .pro-sig-empty-text {
        font-size: 0.75rem;
        font-weight: 500;
      }
      
      .pro-sig-comment {
        width: 100%;
        min-height: 80px;
        border: 2px solid #e2e8f0;
        border-radius: 10px;
        padding: 0.75rem;
        font-family: inherit;
        font-size: 0.8rem;
        resize: none;
        transition: all 0.2s ease;
        background: white;
      }
      
      .pro-sig-comment:focus {
        outline: none;
        border-color: #d21725;
        box-shadow: 0 0 0 3px rgba(210,23,37,0.1);
      }
      
      .pro-sig-comment::placeholder {
        color: #94a3b8;
      }
      
      .pro-sig-footer {
        padding: 0.875rem;
        border-top: 1px solid #e2e8f0;
        display: flex;
        justify-content: flex-end;
        gap: 0.5rem;
        background: white;
      }
      
      /* Signature Popup */
      .pro-popup-overlay {
        display: none;
        position: fixed;
        inset: 0;
        background: rgba(15,23,42,0.5);
        backdrop-filter: blur(4px);
        z-index: 10000;
        align-items: center;
        justify-content: center;
        padding: 1rem;
      }
      
      .pro-popup-overlay.active {
        display: flex;
      }
      
      .pro-popup {
        background: white;
        border-radius: 20px;
        width: 100%;
        max-width: 440px;
        box-shadow: 0 25px 50px rgba(0,0,0,0.25);
        animation: popUp 0.3s ease;
        overflow: hidden;
      }
      
      @keyframes popUp {
        from { opacity: 0; transform: scale(0.95) translateY(20px); }
        to { opacity: 1; transform: scale(1) translateY(0); }
      }
      
      .pro-popup-header {
        padding: 1.25rem;
        border-bottom: 1px solid #e2e8f0;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      
      .pro-popup-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #1e293b;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 0.5rem;
      }
      
      .pro-popup-close {
        width: 36px;
        height: 36px;
        border-radius: 10px;
        border: none;
        background: #f1f5f9;
        color: #64748b;
        font-size: 1.25rem;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s ease;
      }
      
      .pro-popup-close:hover {
        background: #fee2e2;
        color: #dc2626;
      }
      
      .pro-popup-body {
        padding: 1.25rem;
      }
      
      .pro-popup-canvas {
        border: 2px solid #e2e8f0;
        border-radius: 12px;
        overflow: hidden;
        background: white;
      }
      
      .pro-popup-canvas canvas {
        width: 100%;
        height: 180px;
        display: block;
      }
      
      .pro-popup-hint {
        text-align: center;
        font-size: 0.75rem;
        color: #94a3b8;
        margin-top: 0.75rem;
      }
      
      .pro-popup-footer {
        padding: 1rem 1.25rem;
        border-top: 1px solid #e2e8f0;
        display: flex;
        justify-content: flex-end;
        gap: 0.5rem;
        background: #f8fafc;
      }
      
      /* Member Since */
      .pro-member-since {
        text-align: center;
        padding: 1.25rem;
        margin-top: 0.5rem;
        color: #64748b;
        font-size: 0.9rem;
        border-top: 1px solid #e2e8f0;
      }
      
      .pro-member-since strong {
        color: #334155;
      }
      
    </style>
    
    <div class="pro-container">
      <!-- Hero Section -->
      <div class="pro-hero">
        <div class="pro-hero-content">
          <div class="pro-hero-main">
            <div class="pro-avatar">${getInitials()}</div>
            <div class="pro-hero-text">
              <h2 class="pro-name">${escapeHtml(user.full_name || user.username)}</h2>
              <div class="pro-role-badge">
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg>
                ${escapeHtml(getDesignationDisplay())} • ${escapeHtml(getRoleDisplay())}
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Tabs -->
      <div class="pro-tabs">
        <button class="pro-tab active" data-tab="profile" onclick="switchProfileTab('profile')">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg>
          <span>Profile</span>
        </button>
        <button class="pro-tab" data-tab="security" onclick="switchProfileTab('security')">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/></svg>
          <span>Security</span>
        </button>
        <button class="pro-tab" data-tab="signature" onclick="switchProfileTab('signature')">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
          <span>Signature</span>
        </button>
      </div>
      
      <div class="pro-tab-panels">
      <!-- Profile Tab -->
      <div class="pro-tab-content active" data-content="profile">
        <div class="pro-info-list">
          <div class="pro-info-item">
            <div class="pro-info-content">
              <div class="pro-info-label">Username</div>
              <div class="pro-info-value">${escapeHtml(user.username)}</div>
            </div>
          </div>
          <div class="pro-info-item">
            <div class="pro-info-content">
              <div class="pro-info-label">Email Address</div>
              <div class="pro-info-value">${escapeHtml(user.email || 'Not provided')}</div>
            </div>
          </div>
          <div class="pro-info-item pro-info-item--span">
            <div class="pro-info-content">
              <div class="pro-info-label">Job title (HR)</div>
              <div class="pro-info-value">${hrJobTitle}</div>
            </div>
          </div>
          <div class="pro-info-item">
            <div class="pro-info-content">
              <div class="pro-info-label">Annual leave (days)</div>
              <div class="pro-info-value">${annualLeavesDisp}</div>
            </div>
          </div>
          <div class="pro-info-item">
            <div class="pro-info-content">
              <div class="pro-info-label">Other leave (days)</div>
              <div class="pro-info-value">${otherLeavesDisp}</div>
            </div>
          </div>
          <div class="pro-info-item pro-info-item--span">
            <div class="pro-info-content">
              <div class="pro-info-label">Reporting manager</div>
              <div class="pro-info-value">${reportingMgrDisp}</div>
            </div>
          </div>
        </div>

        <div class="pro-profile-edit" style="margin: 0.85rem 0 0; padding: 1rem 1rem; background: #f8fafc; border-radius: 12px; border: 1px solid #e2e8f0;">
          <div style="font-size: 0.82rem; font-weight: 700; color: #334155; margin-bottom: 0.5rem;">Your details</div>
          <p style="font-size: 0.72rem; color: #64748b; margin: 0 0 0.55rem;">Used for your name on documents and tenure on the home dashboard. Job title, leave balances, and reporting manager are maintained by an administrator.</p>
          <div class="pro-profile-edit-grid">
            <label class="pro-mini-lbl"><span style="display:block;margin-bottom:.25rem;font-size:.74rem;color:#64748b;">Full name</span>
              <input type="text" id="profileManagedFullName" style="width:100%;padding:0.5rem 0.65rem;border:1px solid #cbd5e1;border-radius:8px;font-size:0.9rem;box-sizing:border-box;" value="${escapeHtml(user.full_name || '')}" maxlength="120" autocomplete="name" /></label>
            <label class="pro-mini-lbl"><span style="display:block;margin-bottom:.25rem;font-size:.74rem;color:#64748b;">Joined company</span>
              <input type="date" id="profileManagedJoined" style="width:100%;padding:0.5rem 0.65rem;border:1px solid #cbd5e1;border-radius:8px;font-size:0.9rem;box-sizing:border-box;" value="${user.employment_start_date ? escapeHtml(String(user.employment_start_date).slice(0, 10)) : ''}" /></label>
          </div>
          <button type="button" class="pro-btn pro-btn-primary pro-btn-sm" id="profileManagedSaveBtn" style="margin-top: 0.65rem;">Save profile details</button>
          <p id="profileManagedSaveHint" style="font-size: 0.74rem; color: #64748b; margin: 0.5rem 0 0;"></p>
        </div>
        
        <div class="pro-modules-wrap">
          <div class="pro-modules-title">Module Access</div>
          <div class="pro-modules-list">
            ${moduleBadges}
          </div>
        </div>
        
        <div class="pro-member-since">
          Member since <strong>${formatDate(user.created_at).replace(' (GST)', '').split(',')[0]}</strong>
        </div>
      </div>
      
      <!-- Security Tab -->
      <div class="pro-tab-content" data-content="security">
        <div class="pro-security-card ${user.password_changed ? 'success' : 'warning'}">
          <div class="pro-security-icon">${user.password_changed ? '✓' : '!'}</div>
          <div class="pro-security-content">
            <div class="pro-security-title">${user.password_changed ? 'Password is secure' : 'Password change required'}</div>
            <div class="pro-security-desc">${user.password_changed ? 'Your password meets security requirements' : 'Please update your password for security'}</div>
          </div>
          <div class="pro-security-action">
            <button class="pro-btn ${user.password_changed ? 'pro-btn-outline' : 'pro-btn-primary'} pro-btn-sm" onclick="showChangePasswordForm()">
              ${user.password_changed ? 'Change' : 'Update Now'}
            </button>
          </div>
        </div>
        
        <div class="pro-info-list">
          <div class="pro-info-item">
            <div class="pro-info-content">
              <div class="pro-info-label">Account Status</div>
              <div class="pro-info-value" style="color: ${user.is_active ? '#16a34a' : '#dc2626'}">
                ${user.is_active ? '● Active' : '● Inactive'}
              </div>
            </div>
          </div>
          <div class="pro-info-item">
            <div class="pro-info-content">
              <div class="pro-info-label">Role</div>
              <div class="pro-info-value">${escapeHtml(getRoleDisplay())}</div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Signature Tab -->
      <div class="pro-tab-content" data-content="signature">
        <div class="pro-sig-section">
          <div class="pro-sig-header">
            <div class="pro-sig-header-icon"><svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg></div>
            <div class="pro-sig-header-text">
              <h4>Default Signature</h4>
              <p>Used for automatic form signing</p>
            </div>
          </div>
          <div class="pro-sig-body">
            <div class="pro-sig-grid">
              <div class="pro-sig-preview" id="profileSigPreview" title="Click to draw signature">
                <div class="pro-sig-empty" id="profileSigEmpty">
                  <div class="pro-sig-empty-icon"><svg width="26" height="26" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg></div>
                  <div class="pro-sig-empty-text">Tap to sign</div>
                </div>
                <img id="profileSigImage" style="display: none;" alt="Signature">
              </div>
              <textarea class="pro-sig-comment" id="profileDefaultComment" placeholder="Enter default comment for reviews..."></textarea>
            </div>
          </div>
          <div class="pro-sig-footer">
            <button type="button" class="pro-btn pro-btn-danger pro-btn-sm" id="profileRemoveSignature">Remove</button>
            <button type="button" class="pro-btn pro-btn-success pro-btn-sm" id="profileSaveSignature">Save Defaults</button>
          </div>
        </div>
      </div>
      </div><!-- /.pro-tab-panels -->
      
      <!-- Signature Popup -->
      <div class="pro-popup-overlay" id="sigPopupOverlay">
        <div class="pro-popup">
          <div class="pro-popup-header">
            <h3 class="pro-popup-title">Draw Signature</h3>
            <button class="pro-popup-close" id="sigPopupClose">×</button>
          </div>
          <div class="pro-popup-body">
            <div class="pro-popup-canvas">
              <canvas id="profileSignaturePad"></canvas>
            </div>
            <p class="pro-popup-hint">Use mouse or finger to draw your signature</p>
          </div>
          <div class="pro-popup-footer">
            <button type="button" class="pro-btn pro-btn-outline pro-btn-sm" id="profileClearSignature">Clear</button>
            <button type="button" class="pro-btn pro-btn-success pro-btn-sm" id="sigPopupDone">Done</button>
          </div>
        </div>
      </div>
    </div>
  `;
}

// Tab switching function
window.switchProfileTab = function(tabName) {
  document.querySelectorAll('.pro-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.tab === tabName);
  });
  document.querySelectorAll('.pro-tab-content').forEach(content => {
    content.classList.toggle('active', content.dataset.content === tabName);
  });
}

// ===========================================
// Profile Signature Functions
// ===========================================

let profileSignaturePad = null;
let currentSignatureDataUrl = null;

function initProfileSignatureDefaults(user) {
  const canvas = document.getElementById('profileSignaturePad');
  const sigPreview = document.getElementById('profileSigPreview');
  const sigImage = document.getElementById('profileSigImage');
  const sigEmpty = document.getElementById('profileSigEmpty');
  const sigPopupOverlay = document.getElementById('sigPopupOverlay');
  const sigPopupClose = document.getElementById('sigPopupClose');
  const sigPopupDone = document.getElementById('sigPopupDone');
  
  if (!canvas || typeof SignaturePad === 'undefined') return;
  
  profileSignaturePad = new SignaturePad(canvas, {
    backgroundColor: 'rgb(255, 255, 255)',
    penColor: 'rgb(0, 0, 0)',
    minWidth: 1,
    maxWidth: 3,
    throttle: 16
  });

  function resizeCanvas() {
    const ratio = Math.max(window.devicePixelRatio || 1, 1);
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    canvas.width = rect.width * ratio;
    canvas.height = rect.height * ratio;
    const ctx = canvas.getContext('2d');
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.fillStyle = 'rgb(255, 255, 255)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (currentSignatureDataUrl) {
      profileSignaturePad.fromDataURL(currentSignatureDataUrl);
    }
  }

  async function resolveSignatureDataUrl(src) {
    if (!src) return null;
    if (src.startsWith('data:image')) return src;
    try {
      const response = await fetch(src);
      if (!response.ok) return null;
      const blob = await response.blob();
      return await new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => resolve(null);
        reader.readAsDataURL(blob);
      });
    } catch (error) {
      console.warn('Failed to fetch signature URL', error);
      return null;
    }
  }

  function updatePreview(dataUrl) {
    currentSignatureDataUrl = dataUrl;
    if (dataUrl) {
      sigImage.src = dataUrl;
      sigImage.style.display = 'block';
      sigEmpty.style.display = 'none';
      sigPreview.classList.add('has-signature');
    } else {
      sigImage.style.display = 'none';
      sigEmpty.style.display = 'block';
      sigPreview.classList.remove('has-signature');
    }
  }

  // Load existing signature
  if (user.default_signature) {
    resolveSignatureDataUrl(user.default_signature).then((dataUrl) => {
      if (dataUrl) {
        updatePreview(dataUrl);
      }
    });
  }

  // Open popup when clicking preview
  sigPreview.addEventListener('click', () => {
    sigPopupOverlay.classList.add('active');
    setTimeout(() => {
      resizeCanvas();
      if (currentSignatureDataUrl) {
        profileSignaturePad.fromDataURL(currentSignatureDataUrl);
      }
    }, 100);
  });

  // Close popup
  function closePopup() {
    sigPopupOverlay.classList.remove('active');
  }
  sigPopupClose.addEventListener('click', closePopup);
  sigPopupOverlay.addEventListener('click', (e) => {
    if (e.target === sigPopupOverlay) closePopup();
  });

  // Done button - save signature to preview
  sigPopupDone.addEventListener('click', () => {
    if (!profileSignaturePad.isEmpty()) {
      const dataUrl = profileSignaturePad.toDataURL('image/png');
      updatePreview(dataUrl);
    }
    closePopup();
  });

  const commentEl = document.getElementById('profileDefaultComment');
  if (commentEl) commentEl.value = user.default_comment || '';

  const clearBtn = document.getElementById('profileClearSignature');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      profileSignaturePad.clear();
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = 'rgb(255, 255, 255)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    });
  }

  const saveBtn = document.getElementById('profileSaveSignature');
  if (saveBtn) {
    saveBtn.addEventListener('click', async () => {
      const token = localStorage.getItem('access_token');
      if (!token) {
        alert('Please log in again to save your signature.');
        return;
      }
      const payload = {
        signature_data_url: currentSignatureDataUrl || '',
        default_comment: commentEl ? commentEl.value : ''
      };
      try {
        const response = await fetch('/api/auth/signature-default', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify(payload)
        });
        if (response.status === 401) {
          if (confirm('Session expired. Would you like to log in again?')) {
            window.location.href = '/login';
          }
          return;
        }
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Failed to save defaults');
        const userData = localStorage.getItem('user');
        if (userData) {
          const parsed = JSON.parse(userData);
          parsed.default_signature = data.default_signature;
          parsed.default_comment = data.default_comment;
          localStorage.setItem('user', JSON.stringify(parsed));
        }
        saveBtn.textContent = 'Saved!';
        setTimeout(() => { saveBtn.textContent = 'Save'; }, 1500);
      } catch (error) {
        console.error('Save default signature failed', error);
        alert(error.message || 'Failed to save. Please log in again.');
      }
    });
  }

  const removeBtn = document.getElementById('profileRemoveSignature');
  if (removeBtn) {
    removeBtn.addEventListener('click', async () => {
      const token = localStorage.getItem('access_token');
      if (!token) {
        alert('Please log in again.');
        return;
      }
      try {
        const response = await fetch('/api/auth/signature-default', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({ remove_default: true })
        });
        if (response.status === 401) {
          if (confirm('Session expired. Would you like to log in again?')) {
            window.location.href = '/login';
          }
          return;
        }
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Failed to remove defaults');
        if (profileSignaturePad) profileSignaturePad.clear();
        if (commentEl) commentEl.value = '';
        updatePreview(null);
        const userData = localStorage.getItem('user');
        if (userData) {
          const parsed = JSON.parse(userData);
          parsed.default_signature = data.default_signature;
          parsed.default_comment = data.default_comment;
          localStorage.setItem('user', JSON.stringify(parsed));
        }
        removeBtn.textContent = 'Removed!';
        setTimeout(() => { removeBtn.textContent = 'Remove'; }, 1500);
      } catch (error) {
        console.error('Remove default signature failed', error);
        alert(error.message || 'Failed to remove default signature.');
      }
    });
  }
}

function initManagedProfileFields() {
  const btn = document.getElementById('profileManagedSaveBtn');
  const hint = document.getElementById('profileManagedSaveHint');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    const token = localStorage.getItem('access_token');
    const nameEl = document.getElementById('profileManagedFullName');
    const joinedEl = document.getElementById('profileManagedJoined');
    if (!token) {
      if (hint) hint.textContent = 'Please log in again.';
      return;
    }
    btn.disabled = true;
    if (hint) hint.textContent = 'Saving…';
    try {
      const res = await fetch('/api/auth/profile', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          full_name: (nameEl && nameEl.value) ? nameEl.value.trim() : '',
          employment_start_date: (joinedEl && joinedEl.value) ? joinedEl.value : ''
        })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.success) {
        throw new Error(data.error || 'Could not save');
      }
      if (hint) hint.textContent = 'Saved.';
      if (data.user) {
        localStorage.setItem('user', JSON.stringify(data.user));
        if (typeof loadUserWelcome === 'function') {
          loadUserWelcome();
        }
        if (typeof loadDashboardStats === 'function') {
          loadDashboardStats();
        }
      }
    } catch (e) {
      if (hint) hint.textContent = e.message || 'Save failed.';
    } finally {
      btn.disabled = false;
      setTimeout(() => {
        const h = document.getElementById('profileManagedSaveHint');
        if (h && (h.textContent === 'Saved.' || h.textContent === 'Saving…')) h.textContent = '';
      }, 2500);
    }
  });
}

// ===========================================
// Change Password Functions
// ===========================================

window.showChangePasswordForm = function() {
  const profileContent = document.getElementById('profileContent');
  const html = `
    <div style="padding: 1rem;">
      <h3 style="margin-bottom: 1.5rem; text-align: center; color: var(--primary);">Change Password</h3>
      <form id="changePasswordForm" onsubmit="event.preventDefault(); submitChangePassword();">
        <div class="mb-3">
          <label for="currentPassword" class="form-label">Current Password</label>
          <input type="password" id="currentPassword" class="form-control" required placeholder="Enter current password" autocomplete="off" data-1p-ignore="true" data-lpignore="true">
        </div>
        <div class="mb-3">
          <label for="newPassword" class="form-label">New Password</label>
          <input type="password" id="newPassword" class="form-control" required minlength="8" placeholder="Enter new password (min 8 chars)" autocomplete="off" data-1p-ignore="true" data-lpignore="true">
          <p class="contact-modal-note" style="margin-top: 0.25rem;">Must be at least 8 characters long.</p>
        </div>
        <div class="mb-3">
          <label for="confirmNewPassword" class="form-label">Confirm New Password</label>
          <input type="password" id="confirmNewPassword" class="form-control" required minlength="8" placeholder="Confirm new password" autocomplete="off" data-1p-ignore="true" data-lpignore="true">
        </div>
        <div id="changePasswordError" class="alert alert-danger" style="display: none; margin-bottom: 1rem; font-size: 0.9rem;"></div>
        <div id="changePasswordSuccess" class="alert alert-success" style="display: none; margin-bottom: 1rem; font-size: 0.9rem;"></div>
        
        <div style="display: flex; gap: 1rem; margin-top: 2rem;">
          <button type="button" class="btn btn-outline-secondary" onclick="loadProfileData()" style="flex: 1; padding: 0.75rem;">Cancel</button>
          <button type="submit" id="submitPasswordBtn" class="btn btn-primary" style="flex: 2; padding: 0.75rem; font-weight: 600;">Update Password</button>
        </div>
      </form>
    </div>
  `;
  profileContent.innerHTML = html;
};

window.submitChangePassword = async function() {
  const currentPassword = document.getElementById('currentPassword').value;
  const newPassword = document.getElementById('newPassword').value;
  const confirmNewPassword = document.getElementById('confirmNewPassword').value;
  const errorDiv = document.getElementById('changePasswordError');
  const successDiv = document.getElementById('changePasswordSuccess');
  const submitBtn = document.getElementById('submitPasswordBtn');
  
  errorDiv.style.display = 'none';
  successDiv.style.display = 'none';
  
  if (newPassword !== confirmNewPassword) {
    errorDiv.textContent = 'New passwords do not match.';
    errorDiv.style.display = 'block';
    return;
  }
  
  const token = localStorage.getItem('access_token');
  if (!token) {
    errorDiv.textContent = 'You are not logged in.';
    errorDiv.style.display = 'block';
    return;
  }
  
  submitBtn.disabled = true;
  submitBtn.innerHTML = 'Updating...';
  
  try {
    const response = await fetch('/api/auth/change-password', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword
      })
    });
    
    const result = await response.json();
    
    if (!response.ok) {
      throw new Error(result.error || 'Failed to change password');
    }
    
    successDiv.textContent = 'Password updated successfully! Redirecting to login...';
    successDiv.style.display = 'block';
    
    setTimeout(() => {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user_id');
      window.location.href = '/login';
    }, 2000);
    
  } catch (error) {
    console.error('Password change error:', error);
    errorDiv.textContent = error.message;
    errorDiv.style.display = 'block';
    submitBtn.disabled = false;
    submitBtn.innerHTML = 'Update Password';
  }
};

// ===========================================
// Logout Function
// ===========================================

async function handleLogout() {
  try {
    const token = localStorage.getItem('access_token');
    
    if (!token) {
      localStorage.clear();
      window.location.href = '/login';
      return;
    }
    
    await fetch('/api/auth/logout', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      }
    });
    
    localStorage.clear();
    sessionStorage.clear();
    window.location.href = '/login';
    
  } catch (error) {
    console.error('Logout error:', error);
    localStorage.clear();
    sessionStorage.clear();
    window.location.href = '/login';
  }
}

// ===========================================
// Dashboard stats widget (right-side box)
// ===========================================

function dashboardStatHrefFromLabel(label) {
  if (!label) return '/workflow/submitted-forms';
  var L = String(label).toLowerCase();
  if (L.indexOf('inspection') >= 0) return '/inspection/';
  if (L.indexOf('hr form') >= 0 || L.indexOf('my hr') >= 0) return '/hr/';
  if (L.indexOf('document') >= 0) return '/dochub';
  if (L.indexOf('device') >= 0) return '/admin/devices';
  if (L.indexOf('active user') >= 0) return '/admin/team-management';
  if (L.indexOf('days with injaaz') >= 0) return '/workflow/submitted-forms';
  if (L.indexOf('material') >= 0 || L.indexOf('catalog') >= 0) return '/procurement/';
  if (L.indexOf('project') >= 0 || L.indexOf('rfp') >= 0 || L.indexOf('pipeline') >= 0) return '/admin/bd';
  if (L.indexOf('pending') >= 0) return '/workflow/pending-reviews';
  if (L.indexOf('completed') >= 0 || L.indexOf('completion rate') >= 0) return '/workflow/submitted-forms';
  if (L.indexOf('form') >= 0) return '/workflow/submitted-forms';
  return '/workflow/submitted-forms';
}

function bindDashboardStatCard(card) {
  if (!card) return;
  card.onclick = function (e) {
    if (card.hidden) return;
    if (e.target.closest('.dashboard-stat-joined-link')) return;
    e.preventDefault();
    e.stopPropagation();
    var action = card.getAttribute('data-action');
    if (action === 'profile') {
      if (typeof window.openProfileModal === 'function') window.openProfileModal();
      return;
    }
    var href = card.getAttribute('data-href');
    if (href) window.location.assign(href);
  };
}

function applyDashboardStatCardLinks(metrics) {
  if (!Array.isArray(metrics)) return;
  document.querySelectorAll('.dashboard-stat-card--clickable[data-metric-index]').forEach(function (card) {
    var idx = parseInt(card.getAttribute('data-metric-index'), 10);
    var m = metrics[idx];
    var label = m && m.label ? m.label : '';
    var href = (m && m.href) ? String(m.href) : dashboardStatHrefFromLabel(label);
    card.removeAttribute('data-action');
    card.setAttribute('data-href', href);
    if (label) card.setAttribute('title', 'Open ' + label);
    bindDashboardStatCard(card);
  });
  ['stat-card-annual', 'stat-card-sick'].forEach(function (id) {
    var card = document.getElementById(id);
    if (!card || card.hidden) return;
    card.removeAttribute('data-href');
    card.setAttribute('data-action', 'profile');
    card.setAttribute('title', 'View profile');
    bindDashboardStatCard(card);
  });
}

function loadDashboardStats() {
  const widget = document.querySelector('.dashboard-widget');
  if (!widget) return;
  // Review History page populates its widget from submission data, not global stats
  if (document.body.classList.contains('review-dashboard')) return;

  const token = localStorage.getItem('access_token');
  if (!token) return;

  authenticatedFetch('/api/workflow/dashboard-stats')
    .then(function (response) {
      return response.json().then(function (body) {
        return { ok: response.ok, body: body };
      }).catch(function () {
        return { ok: false, body: null };
      });
    })
    .then(function (result) {
      if (!result.ok || !result.body) return;
      // API: hero_metrics + dashboard_role, or legacy forms_submitted / pending_review / ...
      var d = result.body;
      var metrics = d.hero_metrics;
      if (Array.isArray(metrics) && metrics.length) {
        var joinedRow = document.getElementById('stat-label-row-3');
        for (var i = 0; i < 4; i++) {
          var m = metrics[i];
          var lbl = document.getElementById('stat-label-' + i);
          var val = document.getElementById('stat-value-' + i);
          if (lbl && m && m.label) {
            if (i === 3 && joinedRow) {
              var joinedDate = m.joined_date || d.employment_start_date;
              if (joinedDate) {
                joinedRow.innerHTML = escapeHtml(m.label) + ' · Joined <a href="#" id="stat-joined-link-3" class="dashboard-stat-joined-link">' + escapeHtml(joinedDate) + '</a>';
                var joinedLink = document.getElementById('stat-joined-link-3');
                if (joinedLink) {
                  joinedLink.onclick = function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (typeof openProfileModal === 'function') openProfileModal();
                  };
                }
              } else {
                joinedRow.innerHTML = '<span id="stat-label-3">' + escapeHtml(m.label) + '</span>';
              }
            } else {
              lbl.textContent = m.label;
            }
          }
          if (val && m) {
            var v = m.value;
            val.textContent = v != null && v !== '' ? String(v) : '0';
          }
          if (i === 3) {
            var annualCard = document.getElementById('stat-card-annual');
            var sickCard = document.getElementById('stat-card-sick');
            var annualValEl = document.getElementById('leave-annual-value');
            var sickValEl = document.getElementById('leave-sick-value');
            var gridEl = document.getElementById('dashboard-stats-grid');
            var annual = m && m.annual_leave_days != null ? m.annual_leave_days : null;
            var other = m && m.other_leave_days != null ? m.other_leave_days : null;
            if (annualCard && sickCard && annualValEl && sickValEl) {
              if (annual != null || other != null) {
                annualValEl.textContent = annual != null ? String(annual) : '0';
                sickValEl.textContent = other != null ? String(other) : '0';
                annualCard.hidden = false;
                sickCard.hidden = false;
                annualCard.removeAttribute('data-href');
                annualCard.setAttribute('data-action', 'profile');
                sickCard.removeAttribute('data-href');
                sickCard.setAttribute('data-action', 'profile');
                bindDashboardStatCard(annualCard);
                bindDashboardStatCard(sickCard);
                if (gridEl) gridEl.classList.add('has-leave');
              } else {
                annualCard.hidden = true;
                sickCard.hidden = true;
                if (gridEl) gridEl.classList.remove('has-leave');
              }
            }
          }
        }
        applyDashboardStatCardLinks(metrics);
      } else {
        var formsEl = document.getElementById('stat-value-0') || document.getElementById('stat-forms-submitted');
        var pendingEl = document.getElementById('stat-value-1') || document.getElementById('stat-pending-review');
        var usersEl = document.getElementById('stat-value-2') || document.getElementById('stat-active-users');
        var rateEl = document.getElementById('stat-value-3') || document.getElementById('stat-completion-rate');
        if (document.getElementById('stat-label-0')) document.getElementById('stat-label-0').textContent = 'Forms submitted';
        if (document.getElementById('stat-label-1')) document.getElementById('stat-label-1').textContent = 'Pending review';
        if (document.getElementById('stat-label-2')) document.getElementById('stat-label-2').textContent = 'Active users';
        if (document.getElementById('stat-label-3')) document.getElementById('stat-label-3').textContent = 'Completion rate';
        if (formsEl) formsEl.textContent = typeof d.forms_submitted === 'number' ? d.forms_submitted.toLocaleString() : (d.forms_submitted != null ? d.forms_submitted : '0');
        if (pendingEl) pendingEl.textContent = typeof d.pending_review === 'number' ? d.pending_review : (d.pending_review != null ? d.pending_review : '0');
        if (usersEl) usersEl.textContent = typeof d.active_users === 'number' ? d.active_users : (d.active_users != null ? d.active_users : '0');
        if (rateEl) rateEl.textContent = typeof d.completion_rate === 'number' ? d.completion_rate + '%' : (d.completion_rate != null ? d.completion_rate + '%' : '0%');
        var joinedRowFb = document.getElementById('stat-label-row-3');
        if (joinedRowFb) {
          var lblFb = document.getElementById('stat-label-3');
          if (lblFb) joinedRowFb.innerHTML = '<span id="stat-label-3">' + escapeHtml(lblFb.textContent || 'Completion rate') + '</span>';
        }
        var annualCardFb = document.getElementById('stat-card-annual');
        var sickCardFb = document.getElementById('stat-card-sick');
        var gridFb = document.getElementById('dashboard-stats-grid');
        if (annualCardFb) annualCardFb.hidden = true;
        if (sickCardFb) sickCardFb.hidden = true;
        if (gridFb) gridFb.classList.remove('has-leave');
      }
    })
    .catch(function () {});
}

function loadInspectionDashboardStats() {
  var grid = document.getElementById('inspection-stats-grid');
  if (!grid) return;
  var cardCount = grid.querySelectorAll('.dashboard-stat-card').length || 3;

  var token = localStorage.getItem('access_token');
  if (!token) {
    for (var j = 0; j < cardCount; j++) {
      var ve = document.getElementById('insp-stat-value-' + j);
      if (ve) ve.textContent = '—';
    }
    return;
  }

  authenticatedFetch('/api/workflow/inspection-dashboard-stats')
    .then(function (response) {
      return response.json().then(function (body) {
        return { ok: response.ok, body: body };
      }).catch(function () {
        return { ok: false, body: null };
      });
    })
    .then(function (result) {
      var metrics = result.body && result.body.hero_metrics;
      if (!result.ok || !Array.isArray(metrics) || !metrics.length) {
        for (var i = 0; i < cardCount; i++) {
          var vv = document.getElementById('insp-stat-value-' + i);
          if (vv) vv.textContent = '—';
        }
        return;
      }
      for (var k = 0; k < cardCount; k++) {
        var m = metrics[k];
        var lbl = document.getElementById('insp-stat-label-' + k);
        var val = document.getElementById('insp-stat-value-' + k);
        if (lbl && m && m.label) lbl.textContent = m.label;
        if (val && m) {
          var v = m.value;
          val.textContent = v != null && v !== '' ? String(v) : '0';
        } else if (val && !m) {
          val.textContent = '—';
        }
      }
    })
    .catch(function () {
      for (var e = 0; e < cardCount; e++) {
        var el = document.getElementById('insp-stat-value-' + e);
        if (el) el.textContent = '—';
      }
    });
}

// ===========================================
// Initialization
// ===========================================

document.addEventListener('DOMContentLoaded', function() {
  // Main dashboard only: modulesGrid. Module dashboards (HR, Inspection, etc.) use runNavVisibility for consistent nav
  const hasModuleGrid = !!document.getElementById('hrFormsGrid') || !!document.getElementById('inspectionFormsGrid');
  const isDashboardPage = !!document.getElementById('modulesGrid') && !hasModuleGrid;
  const isReviewHistoryPage = document.body.classList.contains('review-dashboard');
  const hasMainNav = document.getElementById('nav') && document.querySelector('#nav .nav-center');

  // Run nav visibility on any page with main dashboard nav (admin, hr, mmr, procurement, etc.)
  function runNavVisibility() {
    const userStr = localStorage.getItem('user');
    if (userStr) {
      try {
        const user = JSON.parse(userStr);
        checkAndShowAdminMenu(user);
        updateModuleVisibility(user);
        if (typeof loadPendingCount === 'function') {
          loadPendingCount(user);
        }
      } catch (e) {
        console.error('Error parsing user from localStorage:', e);
      }
    } else {
      const token = localStorage.getItem('access_token');
      if (token) {
        fetch('/api/auth/me', {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        })
        .then(response => response.json())
        .then(data => {
          if (data.user) {
            localStorage.setItem('user', JSON.stringify(data.user));
            checkAndShowAdminMenu(data.user);
            updateModuleVisibility(data.user);
            if (typeof loadPendingCount === 'function') {
              loadPendingCount(data.user);
            }
          }
        })
        .catch(error => {
          console.error('Failed to fetch user data:', error);
        });
      }
    }
  }

  // Ensure modules section is visible on load (dashboard only)
  if (isDashboardPage) {
    const modulesSection = document.getElementById('modules');
    if (modulesSection) {
      modulesSection.style.display = 'block';
      modulesSection.style.visibility = 'visible';
    }
    
    const modulesGrid = document.getElementById('modulesGrid');
    if (modulesGrid) {
      modulesGrid.style.display = 'grid';
      modulesGrid.style.visibility = 'visible';
    }
    
    loadUserWelcome();
    document.querySelectorAll('.dashboard-stat-card--clickable').forEach(bindDashboardStatCard);
    loadDashboardStats();

    let _moduleGridResizeTimer;
    window.addEventListener('resize', function () {
      clearTimeout(_moduleGridResizeTimer);
      _moduleGridResizeTimer = setTimeout(updateModuleGridLayout, 150);
    });
    
    // Check immediately if user data exists
    const userStr = localStorage.getItem('user');
    const token = localStorage.getItem('access_token');
    if (userStr) {
      try {
        const user = JSON.parse(userStr);
        checkAndShowAdminMenu(user);
        updateModuleVisibility(user);
        if (typeof loadPendingCount === 'function') {
          loadPendingCount(user);
        }
        // Always re-fetch from server to pick up role/access changes and refresh stale cache
        if (token) {
          fetch('/api/auth/me', { headers: { 'Authorization': `Bearer ${token}` } })
            .then(function(r) { return r.ok ? r.json() : null; })
            .then(function(data) {
              if (data && data.user) {
                localStorage.setItem('user', JSON.stringify(data.user));
                checkAndShowAdminMenu(data.user);
                updateModuleVisibility(data.user);
                if (typeof loadPendingCount === 'function') {
                  loadPendingCount(data.user);
                }
              }
            })
            .catch(function() {});
        }
      } catch (e) {
        console.error('Error parsing user from localStorage:', e);
      }
    } else if (token) {
      fetch('/api/auth/me', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      .then(response => response.json())
      .then(data => {
        if (data.user) {
          localStorage.setItem('user', JSON.stringify(data.user));
          checkAndShowAdminMenu(data.user);
          updateModuleVisibility(data.user);
          if (typeof loadPendingCount === 'function') {
            loadPendingCount(data.user);
          }
        }
      })
      .catch(error => {
        console.error('Failed to fetch user data:', error);
      });
    }
  } else if (isReviewHistoryPage || hasMainNav) {
    loadUserWelcome();
    runNavVisibility();
    if (document.getElementById('inspection-stats-grid')) {
      loadInspectionDashboardStats();
    }
  }

  // Enhanced scroll effect
  const nav = document.getElementById('nav');
  if (nav) {
    window.addEventListener('scroll', () => {
      if (window.pageYOffset > 50) {
        nav.classList.add('scrolled');
      } else {
        nav.classList.remove('scrolled');
      }
    });
  }
  
  // Profile link click handler
  const profileLink = document.getElementById('profileLink');
  if (profileLink) {
    profileLink.addEventListener('click', function(e) {
      e.preventDefault();
      openProfileModal();
    });
  }

  // Close modal with Escape key
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      closeProfileModal();
    }
  });
  
  // Smooth scroll for anchor links (exclude Profile which opens modal)
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    if (anchor.id === 'profileLink') return;
    anchor.addEventListener('click', function (e) {
      const href = this.getAttribute('href');
      if (!href || href === '#') return;
      /* href may change after hydrate (e.g. # → /hr/download-pdf/...) — only intercept fragment jumps */
      if (!href.startsWith('#')) return;
      e.preventDefault();
      const target = document.querySelector(href);
      if (target) {
        target.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }
    });
  });
  
  // Load pending count for badge (only on dashboard)
  if (isDashboardPage) {
    const userDataForNotifications = localStorage.getItem('user');
    if (userDataForNotifications) {
      try {
        const userData = JSON.parse(userDataForNotifications);
        if (typeof loadPendingCount === 'function') {
          loadPendingCount(userData);
        }
      } catch (e) {
        console.error('Error parsing user data for notifications:', e);
      }
    }
  }
  
  // Mobile menu toggle - uses drawer outside nav (avoids backdrop-filter containing block)
  const mobileMenuToggle = document.getElementById('mobileMenuToggle');
  const navMenu = document.querySelector('.nav-menu');
  const mobileMenuDrawer = document.getElementById('mobileMenuDrawer');
  const mobileMenuDrawerList = document.getElementById('mobileMenuDrawerList');
  const mobileOverlay = document.getElementById('mobileOverlay');

  function closeMobileMenu() {
    if (mobileMenuToggle) {
      mobileMenuToggle.classList.remove('active');
      mobileMenuToggle.classList.remove('is-hint-paused');
      mobileMenuToggle.setAttribute('aria-expanded', 'false');
    }
    if (mobileMenuDrawer) {
      mobileMenuDrawer.classList.remove('active');
      mobileMenuDrawer.setAttribute('aria-hidden', 'true');
    }
    if (mobileOverlay) mobileOverlay.classList.remove('active');
    document.body.style.overflow = '';
  }

  function populateDrawer() {
    if (!navMenu || !mobileMenuDrawerList) return;
    mobileMenuDrawerList.innerHTML = '';
    Array.from(navMenu.children).forEach(function(li) {
      if (!li || li.tagName !== 'LI') return;
      if (getComputedStyle(li).display === 'none') return;
      var clone = li.cloneNode(true);
      clone.querySelectorAll('[id]').forEach(function(el) { el.removeAttribute('id'); });
      mobileMenuDrawerList.appendChild(clone);
    });
  }

  function openMobileMenu() {
    populateDrawer();
    if (mobileMenuToggle) {
      mobileMenuToggle.classList.add('active');
      mobileMenuToggle.classList.add('is-hint-paused');
      mobileMenuToggle.setAttribute('aria-expanded', 'true');
    }
    if (mobileMenuDrawer) {
      mobileMenuDrawer.classList.add('active');
      mobileMenuDrawer.setAttribute('aria-hidden', 'false');
    }
    if (mobileOverlay) mobileOverlay.classList.add('active');
    document.body.style.overflow = 'hidden';
  }

  if (mobileMenuToggle && mobileMenuDrawer) {
    mobileMenuToggle.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      const isOpen = mobileMenuDrawer.classList.contains('active');
      if (isOpen) {
        closeMobileMenu();
      } else {
        openMobileMenu();
      }
    });
  }

  if (mobileOverlay) {
    mobileOverlay.addEventListener('click', closeMobileMenu);
  }

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && mobileMenuDrawer && mobileMenuDrawer.classList.contains('active')) {
      closeMobileMenu();
    }
  });

  if (mobileMenuDrawerList) {
    mobileMenuDrawerList.addEventListener('click', function(e) {
      var a = e.target.closest('a');
      if (!a) return;
      var parentLi = a.closest('li');
      if (
        parentLi &&
        parentLi.classList.contains('has-submenu') &&
        parentLi.classList.contains('has-submitted-dropdown') &&
        !a.closest('.nav-submenu')
      ) {
        e.preventDefault();
        parentLi.classList.toggle('open');
        return;
      }
      var text = (a.textContent || '').trim().toLowerCase();
      if (text === 'profile') {
        e.preventDefault();
        if (typeof openProfileModal === 'function') openProfileModal();
        closeMobileMenu();
      } else if (a.getAttribute('href') === '#' || a.getAttribute('href') === 'javascript:void(0)') {
        closeMobileMenu();
      } else {
        closeMobileMenu();
      }
    });
  }

  const submittedNavItem = document.getElementById('submitted-forms-menu-item');
  if (submittedNavItem) {
    const submittedTopLink = submittedNavItem.querySelector('a');
    if (submittedTopLink) {
      submittedTopLink.addEventListener('click', function(e) {
        if (!submittedNavItem.classList.contains('has-submitted-dropdown')) return;
        // Desktop / fine pointer: rely on CSS :hover for the menu; allow normal navigation / modified clicks.
        const useClickToggle =
          window.matchMedia('(hover: none), (pointer: coarse)').matches;
        if (!useClickToggle) return;
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        submittedNavItem.classList.toggle('open');
      });
    }
    document.addEventListener('click', function(e) {
      if (!submittedNavItem.classList.contains('open')) return;
      if (!submittedNavItem.contains(e.target)) {
        submittedNavItem.classList.remove('open');
      }
    });
  }
  
  // Logout functionality
  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', handleLogout);
  }
});

// ===========================================
// Notification System
// ===========================================

function initNotifications() {
  const notificationBtn = document.getElementById('notificationBtn');
  const notificationDropdown = document.getElementById('notificationDropdown');
  const markAllReadBtn = document.getElementById('markAllRead');
  
  if (!notificationBtn || !notificationDropdown) return;
  if (notificationBtn.dataset.injaazNotifBound === '1') return;
  notificationBtn.dataset.injaazNotifBound = '1';

  // Toggle dropdown
  notificationBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    notificationDropdown.classList.toggle('show');
    if (notificationDropdown.classList.contains('show')) {
      loadNotifications();
    }
  });
  
  // Close dropdown when clicking outside
  document.addEventListener('click', function(e) {
    if (!notificationDropdown.contains(e.target) && !notificationBtn.contains(e.target)) {
      notificationDropdown.classList.remove('show');
    }
  });
  
  // Mark all as read
  if (markAllReadBtn) {
    markAllReadBtn.addEventListener('click', async function() {
      try {
        const response = await authenticatedFetch('/hr/api/notifications/mark-all-read', {
          method: 'POST'
        });
        if (response.ok) {
          loadNotifications();
          updateNotificationBadge(0);
        }
      } catch (error) {
        console.error('Error marking all as read:', error);
      }
    });
  }
  
  // Load initial notification count
  loadNotificationCount();
  
  // Poll for new notifications every 30 seconds
  setInterval(loadNotificationCount, 30000);
}

async function loadNotificationCount() {
  const badge = document.getElementById('notificationBadge');
  if (!badge) return;
  
  try {
    const token = localStorage.getItem('access_token');
    if (!token) return;
    
    const response = await authenticatedFetch('/hr/api/notifications/unread-count');
    if (response.ok) {
      const data = await response.json();
      updateNotificationBadge(data.unread_count || 0);
    }
  } catch (error) {
    console.error('Error loading notification count:', error);
  }
}

function updateMobileMenuHint(count) {
  const btn = document.getElementById('mobileMenuToggle');
  if (!btn) return;
  if (count > 0) {
    btn.classList.add('has-unread-hint');
    btn.setAttribute('aria-label', `Toggle menu (${count} pending)`);
  } else {
    btn.classList.remove('has-unread-hint');
    btn.classList.remove('is-hint-paused');
    btn.setAttribute('aria-label', 'Toggle menu');
  }
}

function updateNotificationBadge(count) {
  const badge = document.getElementById('notificationBadge');
  if (!badge) return;
  
  if (count > 0) {
    badge.textContent = count > 99 ? '99+' : count;
    badge.style.display = 'flex';
  } else {
    badge.style.display = 'none';
  }
}

async function loadNotifications() {
  const notificationList = document.getElementById('notificationList');
  if (!notificationList) return;
  
  try {
    const token = localStorage.getItem('access_token');
    if (!token) return;
    
    const response = await authenticatedFetch('/hr/api/notifications');
    if (!response.ok) throw new Error('Failed to load notifications');
    
    const data = await response.json();
    
    if (data.notifications && data.notifications.length > 0) {
      notificationList.innerHTML = data.notifications.map(n => {
        const isInspection = (n.notification_type || '').startsWith('inspection_');
        const iconClass = n.notification_type.includes('approved') ? 'approved' : 
                          n.notification_type.includes('rejected') ? 'rejected' :
                          isInspection ? 'pending' : 'info';
        const iconEmoji = n.notification_type.includes('approved') ? '✓' : 
                          n.notification_type.includes('rejected') ? '✕' :
                          isInspection ? '📋' : 'ℹ';
        const createdAt = parseUtcInstantForRelative(n.created_at);
        const timeAgo = createdAt ? getTimeAgo(createdAt) : '';
        
        return `
          <div class="notification-item ${n.is_read ? '' : 'unread'}" onclick="markNotificationRead(${n.id}, '${(n.submission_id || '').replace(/'/g, "\\'")}', '${(n.notification_type || '').replace(/'/g, "\\'")}')">
            <div class="notification-icon ${iconClass}">${iconEmoji}</div>
            <div class="notification-content">
              <div class="notification-title">${escapeHtml(n.title)}</div>
              <div class="notification-message">${escapeHtml(n.message)}</div>
              <div class="notification-time">${timeAgo}</div>
            </div>
          </div>
        `;
      }).join('');
      
      updateNotificationBadge(data.unread_count || 0);
    } else {
      notificationList.innerHTML = '<div class="notification-empty">No notifications yet</div>';
    }
  } catch (error) {
    console.error('Error loading notifications:', error);
    notificationList.innerHTML = '<div class="notification-empty">Error loading notifications</div>';
  }
}

async function markNotificationRead(id, submissionId, notificationType) {
  try {
    await authenticatedFetch(`/hr/api/notifications/${id}/read`, {
      method: 'POST'
    });
    
    // Refresh notifications
    loadNotifications();
    loadNotificationCount();
    
    // Navigate based on notification type when submission exists
    if (submissionId) {
      if (notificationType === 'gm_approval_pending') {
        window.location.href = '/hr/gm-approval';
        return;
      }
      if (notificationType === 'hr_mgmt_chain_signoff') {
        window.location.href = '/hr/mgmt-sign/' + encodeURIComponent(submissionId);
        return;
      }
      if (notificationType === 'hr_replacement_signoff') {
        window.location.href = '/hr/replacement-sign/' + encodeURIComponent(submissionId);
        return;
      }
      if (notificationType === 'hr_replacement_complete') {
        window.location.href = '/hr/my-requests';
        return;
      }
      if (notificationType && notificationType.startsWith('inspection_')) {
        // Approval-pending notifications go straight to the form so the
        // reviewer can read items, comment, and sign in one click.
        if (notificationType === 'inspection_approval_pending') {
          window.location.href = submissionId
            ? '/workflow/inspection/' + encodeURIComponent(submissionId)
            : '/workflow/pending-reviews';
          return;
        }
        // Approved/rejected notifications open the submitter's record.
        if (notificationType === 'inspection_approved' || notificationType === 'inspection_rejected') {
          window.location.href = submissionId
            ? '/workflow/inspection/' + encodeURIComponent(submissionId)
            : '/workflow/submitted-forms?scope=inspection';
          return;
        }
        window.location.href = '/workflow/pending-reviews';
        return;
      }
      window.location.href = '/hr/';
    }
  } catch (error) {
    console.error('Error marking notification as read:', error);
  }
}

window.__hrLastHrSubmissionId = '';
window.hrGoToSubmittedRequest = function hrGoToSubmittedRequest() {
  let id = String(window.__hrLastHrSubmissionId || '').trim();
  if (!id) {
    const el = document.getElementById('submissionId');
    id = el ? String(el.textContent || '').trim() : '';
  }
  window.location.href = id
    ? '/hr/my-requests?submission=' + encodeURIComponent(id)
    : '/hr/my-requests';
};

/** Parse API timestamps: naive ISO strings from the server are stored as UTC (SQLAlchemy _utcnow). */
function parseUtcInstantForRelative(iso) {
  if (iso == null || iso === '') return null;
  let str = String(iso).trim().replace(' ', 'T');
  const hasTz = /[zZ]$/.test(str) || /[+-]\d{2}:?\d{2}$/.test(str);
  if (!hasTz) str += 'Z';
  const d = new Date(str);
  return Number.isNaN(d.getTime()) ? null : d;
}

function getTimeAgo(date) {
  const now = new Date();
  const seconds = Math.floor((now - date) / 1000);

  if (seconds < 0) return 'Just now';
  if (seconds < 60) return 'Just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)} day${Math.floor(seconds / 86400) > 1 ? 's' : ''} ago`;
  return date.toLocaleDateString();
}

(function bootstrapNotificationsBell() {
  if (typeof initNotifications !== 'function') return;
  function bind() {
    initNotifications();
  }
  bind();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  }
})();
