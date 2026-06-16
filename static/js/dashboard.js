/**
 * Injaaz Dashboard JavaScript
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

function isAppAdmin(user) {
  if (!user) return false;
  return String(user.role || '').trim().toLowerCase() === 'admin';
}

function accessFlagOn(user, key) {
  if (!user) return false;
  const v = user[key];
  return v === true || v === 1;
}

function readCachedUser() {
  try {
    const raw = localStorage.getItem('user');
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

/** Always prefer server profile when a JWT exists (fixes stale localStorage hiding admin modules). */
function refreshCurrentUser(callback) {
  const token = localStorage.getItem('access_token');
  if (!token) {
    const cached = readCachedUser();
    if (callback) callback(cached);
    return Promise.resolve(cached);
  }
  return fetch('/api/auth/me', {
    headers: { Authorization: 'Bearer ' + token }
  })
    .then(function (response) {
      if (!response.ok) throw new Error('auth_me_' + response.status);
      return response.json();
    })
    .then(function (data) {
      if (data && data.user) {
        localStorage.setItem('user', JSON.stringify(data.user));
        if (callback) callback(data.user);
        return data.user;
      }
      const cached = readCachedUser();
      if (callback) callback(cached);
      return cached;
    })
    .catch(function (err) {
      console.warn('Failed to refresh user from server:', err);
      const cached = readCachedUser();
      if (callback) callback(cached);
      return cached;
    });
}

function applyUserSession(user) {
  if (!user) return;
  applyNavWelcome(user);
  checkAndShowAdminMenu(user);
  updateModuleVisibility(user);
  if (typeof loadPendingCount === 'function') {
    loadPendingCount(user);
  }
}

function isNavWelcomeCompact() {
  return window.matchMedia('(max-width: 600px)').matches;
}

function getNavWelcomeFirstName(user) {
  const raw = (user && (user.full_name || user.username)) || '';
  const trimmed = String(raw).trim();
  if (!trimmed) return 'there';
  return trimmed.split(/\s+/)[0];
}

/** Desktop: "Welcome, Full Name!" — phone (≤600px): "Hi, FirstName" */
function formatNavWelcome(user) {
  const displayName = (user && (user.full_name || user.username)) || '';
  if (!displayName) {
    return isNavWelcomeCompact() ? 'Hi' : 'Injaaz Application';
  }
  if (isNavWelcomeCompact()) {
    return `Hi, ${getNavWelcomeFirstName(user)}`;
  }
  return `Welcome, ${displayName}!`;
}

function applyNavWelcome(user) {
  const welcomeText = document.getElementById('welcome-text');
  if (!welcomeText) return;
  welcomeText.textContent = formatNavWelcome(user);
  welcomeText.classList.toggle('nav-welcome--compact', isNavWelcomeCompact());
  welcomeText.setAttribute('title', (user && (user.full_name || user.username)) || '');
}

// Load and display user welcome message
function loadUserWelcome() {
  try {
    const cached = readCachedUser();
    if (cached) applyUserSession(cached);
    refreshCurrentUser(applyUserSession);
  } catch (error) {
    console.error('Error loading user welcome:', error);
  }
}

function userHasBdEmailAccess(user) {
  if (!user) return false;
  if (isAppAdmin(user)) return true;
  if (user.designation === 'business_development') return true;
  return accessFlagOn(user, 'access_business_development');
}

function userHasInspectionNavAccess(user) {
  if (!user) return false;
  if (isAppAdmin(user)) return true;
  return accessFlagOn(user, 'access_hvac') || accessFlagOn(user, 'access_civil') || accessFlagOn(user, 'access_cleaning');
}

function userHasHrNavAccess(user) {
  if (!user) return false;
  if (isAppAdmin(user)) return true;
  if (accessFlagOn(user, 'access_hr')) return true;
  const d = (user.designation || '').trim().toLowerCase();
  if (d === 'hr_manager' || d === 'general_manager') return true;
  return false;
}

function userHasSubmittedFormsModuleAccess(user) {
  if (!user) return false;
  if (isAppAdmin(user)) return true;
  // Every logged-in user can open My submitted forms for items they submitted.
  return true;
}

function userHasDocHubNavAccess(user) {
  if (!user) return false;
  if (isAppAdmin(user)) return true;
  if (user.can_access_dochub === false) return false;
  return true;
}

function userHasReportGenerationNavAccess(user) {
  if (!user) return false;
  if (isAppAdmin(user)) return true;
  return accessFlagOn(user, 'access_report_generation');
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
    tktEl.style.display = (user && (isAppAdmin(user) || accessFlagOn(user, 'access_ticketing'))) ? 'list-item' : 'none';
  }
  const qhsiEl = document.getElementById('qhsi-menu-item');
  if (qhsiEl) {
    qhsiEl.style.display = (user && (isAppAdmin(user) || accessFlagOn(user, 'access_qhsi'))) ? 'list-item' : 'none';
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
    adminMenuItem.style.display = (user && isAppAdmin(user)) ? 'list-item' : 'none';
  }
  if (deviceMgmtMenuItem) {
    deviceMgmtMenuItem.style.display = (user && isAppAdmin(user)) ? 'list-item' : 'none';
  }
  if (bdModuleMenuItem) {
    bdModuleMenuItem.style.display = (user && isAppAdmin(user)) ? 'list-item' : 'none';
  }

  // Legacy Review History nav is retired in favor of unified Submitted Forms.
  if (historyMenuItem) {
    historyMenuItem.style.display = 'none';
  }

  applyProfileBasedNavVisibility(user);
  
  if (user && !user.role) {
    refreshCurrentUser(applyUserSession);
  }
}

// ===========================================
// Module Visibility Functions
// ===========================================

function isModuleCardVisible(card) {
  if (!card || !card.classList.contains('module-card')) return false;
  const computed = window.getComputedStyle(card);
  if (computed.display === 'none' || computed.visibility === 'hidden') return false;
  if (card.style.display === 'none' || card.style.visibility === 'hidden') return false;
  return true;
}

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
  const visible = cards.filter(isModuleCardVisible);

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
  
  const isAdmin = isAppAdmin(user);
  
  // Check Inspection Form access (HVAC, Civil, or Cleaning)
  const inspectionCard = document.getElementById('module-inspection');
  if (inspectionCard) {
    const hasInspectionAccess = isAdmin || accessFlagOn(user, 'access_hvac') || accessFlagOn(user, 'access_civil') || accessFlagOn(user, 'access_cleaning');
    inspectionCard.style.display = hasInspectionAccess ? 'block' : 'none';
    inspectionCard.style.visibility = hasInspectionAccess ? 'visible' : 'hidden';
  }
  
  const submittedFormsCard = document.getElementById('module-submitted-forms');
  const submittedFormsMenuItem = document.getElementById('submitted-forms-menu-item');
  const showSubmittedFormsMod = userHasSubmittedFormsModuleAccess(user);
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
    const showBdEmail = userHasBdEmailAccess(user);
    bdEmailCard.style.display = showBdEmail ? 'block' : 'none';
    bdEmailCard.style.visibility = showBdEmail ? 'visible' : 'hidden';
  }

  // Check Device Management access (admin only)
  const deviceMgmtCard = document.getElementById('module-device-management');
  if (deviceMgmtCard) {
    deviceMgmtCard.style.display = isAdmin ? 'block' : 'none';
    deviceMgmtCard.style.visibility = isAdmin ? 'visible' : 'hidden';
  }

  // Check Business Development module access (admin only)
  const bdCard = document.getElementById('module-bd');
  if (bdCard) {
    bdCard.style.display = isAdmin ? 'block' : 'none';
    bdCard.style.visibility = isAdmin ? 'visible' : 'hidden';
  }

  // HR Module: match admin "HR module" flag and HR/GM designations (see /hr/ hub routing)
  const hrCard = document.getElementById('module-hr');
  if (hrCard) {
    const showHr = userHasHrNavAccess(user);
    hrCard.style.display = showHr ? 'block' : 'none';
    hrCard.style.visibility = showHr ? 'visible' : 'hidden';
  }

  // Check Procurement Module access
  const procurementCard = document.getElementById('module-procurement');
  const procurementMenuItem = document.getElementById('procurement-menu-item');
  const hasProcurementAccess = isAdmin || accessFlagOn(user, 'access_procurement_module');
  if (procurementCard) {
    procurementCard.style.display = hasProcurementAccess ? 'block' : 'none';
    procurementCard.style.visibility = hasProcurementAccess ? 'visible' : 'hidden';
  }
  if (procurementMenuItem) {
    procurementMenuItem.style.display = hasProcurementAccess ? 'list-item' : 'none';
  }

  // Service tickets (same rule as main_navbar ticketing-menu-item)
  const ticketingCard = document.getElementById('module-ticketing');
  if (ticketingCard) {
    const showTicketing = isAdmin || accessFlagOn(user, 'access_ticketing');
    ticketingCard.style.display = showTicketing ? 'block' : 'none';
    ticketingCard.style.visibility = showTicketing ? 'visible' : 'hidden';
  }

  const qhsiCard = document.getElementById('module-qhsi');
  const qhsiMenuItem = document.getElementById('qhsi-menu-item');
  const showQhsi = isAdmin || accessFlagOn(user, 'access_qhsi');
  if (qhsiCard) {
    qhsiCard.style.display = showQhsi ? 'block' : 'none';
    qhsiCard.style.visibility = showQhsi ? 'visible' : 'hidden';
  }
  if (qhsiMenuItem) {
    qhsiMenuItem.style.display = showQhsi ? 'list-item' : 'none';
  }

  // Check Report Generation / MMR hub
  const reportGenCard = document.getElementById('module-report-generation');
  if (reportGenCard) {
    const showReport = userHasReportGenerationNavAccess(user);
    reportGenCard.style.display = showReport ? 'block' : 'none';
    reportGenCard.style.visibility = showReport ? 'visible' : 'hidden';
  }
  
  const modulesGrid = document.getElementById('modulesGrid');
  const modulesSection = document.getElementById('modules');
  if (modulesSection) {
    const existingMsg = modulesSection.querySelector('.no-access-message');
    // Only the home dashboard uses #modulesGrid; inspection/HR hubs use their own grids.
    if (!modulesGrid) {
      if (existingMsg) existingMsg.remove();
    } else {
      const visibleCount = Array.from(modulesGrid.children).filter(isModuleCardVisible).length;
      if (visibleCount === 0) {
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
  }

  updateModuleGridLayout();

  if (document.body.classList.contains('page-dashboard') && document.getElementById('modulesGrid')) {
    scheduleDashboardModuleEntrance();
  }

  applyProfileBasedNavVisibility(user);
}

function getVisibleModuleCards(modulesGrid) {
  if (!modulesGrid) return [];
  return Array.from(modulesGrid.children).filter(isModuleCardVisible);
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
  
  if (user && isAppAdmin(user)) {
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

let _profileModalScrollY = 0;

function lockProfileModalPageScroll() {
  _profileModalScrollY = window.scrollY || window.pageYOffset || 0;
  document.documentElement.classList.add('profile-modal-open');
  document.body.classList.add('profile-modal-open');
}

function unlockProfileModalPageScroll() {
  document.documentElement.classList.remove('profile-modal-open');
  document.body.classList.remove('profile-modal-open');
  window.scrollTo(0, _profileModalScrollY);
}

function bindProfileModalScrollTrap() {
  const modal = document.getElementById('profileModal');
  if (!modal || modal.dataset.scrollTrapBound === '1') return;
  modal.dataset.scrollTrapBound = '1';
  modal.addEventListener('wheel', function (e) {
    if (e.target === modal) e.preventDefault();
  }, { passive: false });
  modal.addEventListener('touchmove', function (e) {
    if (e.target === modal) e.preventDefault();
  }, { passive: false });
}

window.openProfileModal = function() {
  const modal = document.getElementById('profileModal');
  if (modal) {
    bindProfileModalScrollTrap();
    modal.classList.add('active');
    lockProfileModalPageScroll();
    loadProfileData();
  }
};

window.closeProfileModal = function() {
  const modal = document.getElementById('profileModal');
  if (modal) {
    modal.classList.remove('active');
    unlockProfileModalPageScroll();
  }
};

function loadProfileData() {
  const profileContent = document.getElementById('profileContent');
  const token = localStorage.getItem('access_token');
  const cachedUser = localStorage.getItem('user');

  let cachedParsed = null;
  if (cachedUser) {
    try {
      cachedParsed = JSON.parse(cachedUser);
    } catch (e) {
      console.warn('Failed to parse cached user data');
    }
  }

  if (cachedParsed) {
    displayProfileData(cachedParsed);
    checkAndShowAdminMenu(cachedParsed);
    updateModuleVisibility(cachedParsed);
  }

  if (!token) {
    if (!cachedParsed) {
      profileContent.innerHTML = '<div style="text-align: center; padding: 2rem;"><p style="color: var(--text-light);">Please log in to view your profile.</p></div>';
    }
    return;
  }

  if (!cachedParsed) {
    profileContent.innerHTML = '<div style="text-align: center; padding: 2rem;"><div class="spinner" style="border: 4px solid rgba(18, 84, 53, 0.1); border-top: 4px solid var(--primary); border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto;"></div><p style="margin-top: 1rem; color: var(--text-light);">Loading profile...</p></div>';
  }

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
    if (isAppAdmin(user) || user.access_hvac) modules.push('HVAC & MEP');
    if (isAppAdmin(user) || user.access_civil) modules.push('Civil Works');
    if (isAppAdmin(user) || user.access_cleaning) modules.push('Cleaning');
    if (userHasHrNavAccess(user)) modules.push('HR');
    if (isAppAdmin(user) || user.access_procurement_module) modules.push('Procurement');
    if (isAppAdmin(user) || user.designation === 'business_development' || user.access_business_development) modules.push('Business Development');
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

const PROFILE_ICONS = {
  user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
  mail: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>',
  briefcase: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M3 12h18"/></svg>',
  manager: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="m16 11 2 2 4-4"/></svg>',
  leave: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>',
  clipboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="3" width="8" height="4" rx="1"/><path d="M9 5H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-3"/><path d="M9 12h6M9 16h4"/></svg>',
  shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
  role: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2 9.5 8.5 3 9l5 4.5L6.5 21 12 17l5.5 4L16 13.5 21 9l-6.5-.5z"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m20 6-11 11-5-5"/></svg>',
  warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.9 1.8 18a1.8 1.8 0 0 0 1.5 2.7h17.4a1.8 1.8 0 0 0 1.5-2.7L13.7 3.9a1.8 1.8 0 0 0-3.1 0z"/><path d="M12 9v4M12 17h.01"/></svg>',
  pen: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>',
  grid: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/></svg>',
  hvac: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 8a4 4 0 0 0-4 4"/><path d="M20 9a8 8 0 0 0-13.6-5.7"/><path d="M4.2 11A8 8 0 0 0 12 20a8 8 0 0 0 8-7"/><circle cx="12" cy="12" r="2"/></svg>',
  civil: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9.5 12 4l9 5.5V20H3z"/><path d="M9 20V12h6v8"/></svg>',
  cleaning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 22V12c0-1.1.9-2 2-2h1V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v6h1a2 2 0 0 1 2 2v10"/><path d="M3 22h18"/><path d="M9 22V16h6v6"/></svg>',
  hr_mod: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
  procurement: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>',
  biz_dev: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
  reports: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m7 16 4-4 4 4 5-5"/></svg>',
  phone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
  close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>'
};

function getProfileCardHTML(user, getInitials, getDesignationDisplay, getRoleDisplay, getModuleAccess, formatDate) {
  const I = PROFILE_ICONS;
  const modules = [];
  if (isAppAdmin(user) || user.access_hvac) modules.push({ name: 'HVAC & MEP', desc: 'Mechanical, electrical & plumbing', icon: 'hvac', color: '#3b82f6', bg: '#eff6ff' });
  if (isAppAdmin(user) || user.access_civil) modules.push({ name: 'Civil Works', desc: 'Construction & site management', icon: 'civil', color: '#8b5cf6', bg: '#f5f3ff' });
  if (isAppAdmin(user) || user.access_cleaning) modules.push({ name: 'Cleaning', desc: 'Facility hygiene & maintenance', icon: 'cleaning', color: '#10b981', bg: '#ecfdf5' });
  if (userHasHrNavAccess(user)) modules.push({ name: 'HR', desc: 'People & workforce management', icon: 'hr_mod', color: '#f59e0b', bg: '#fffbeb' });
  if (isAppAdmin(user) || user.access_procurement_module) modules.push({ name: 'Procurement', desc: 'Purchasing & vendor tracking', icon: 'procurement', color: '#7c3aed', bg: '#faf5ff' });
  if (isAppAdmin(user) || user.designation === 'business_development' || user.access_business_development) modules.push({ name: 'Business Development', desc: 'Proposals & client pipeline', icon: 'biz_dev', color: '#0d9488', bg: '#f0fdfa' });
  if (userHasReportGenerationNavAccess(user)) modules.push({ name: 'Report Generation', desc: 'Analytics & export tools', icon: 'reports', color: '#0369a1', bg: '#eff6ff' });
  
  const moduleBadges = modules.length > 0 
    ? modules.map(m => `
      <div class="pro-mod-card">
        <div class="pro-mod-icon" style="background:${m.bg};color:${m.color};">${I[m.icon]}</div>
        <div class="pro-mod-body">
          <div class="pro-mod-name">${escapeHtml(m.name)}</div>
          <div class="pro-mod-desc">${escapeHtml(m.desc)}</div>
        </div>
        <div class="pro-mod-check" style="color:${m.color}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="m20 6-11 11-5-5"/></svg></div>
      </div>`).join('')
    : '<p class="pro-no-access">No modules assigned</p>';

  const hrJobTitle = escapeHtml(user.job_designation || '—');
  const annualLeavesDisp = user.annual_leave_days != null ? escapeHtml(String(user.annual_leave_days)) : '—';
  const otherLeavesDisp = user.other_leave_days != null ? escapeHtml(String(user.other_leave_days)) : '—';
  const rm = user.reporting_manager;
  const reportingMgrDisp = rm
    ? `${escapeHtml(rm.full_name || rm.username || '')}${rm.email ? `<span style="display:block;font-size:0.8rem;color:#64748b;margin-top:2px;">${escapeHtml(rm.email)}</span>` : ''}`
    : '—';

  return `
    <style>
      /* Profile Modal - iOS inspired two-pane */
      .pro-container {
        font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Inter', 'Segoe UI', sans-serif;
        width: 100%;
        max-width: 100%;
        padding: 0;
        box-sizing: border-box;
        background: #ffffff;
        height: 100%;
      }

      .pro-shell {
        display: flex;
        align-items: stretch;
        height: min(620px, 78vh);
        max-height: 78vh;
        background: #ffffff;
      }

      /* The redesigned header carries its own close button */
      #profileModal .contact-modal-close {
        display: none !important;
      }

      /* Left rail */
      .pro-rail {
        width: 232px;
        flex-shrink: 0;
        display: flex;
        flex-direction: column;
        background: #f7f7fa;
        border-right: 1px solid #e5e5ea;
        padding: 1.25rem 0.85rem 1rem;
        box-sizing: border-box;
      }

      .pro-rail-head {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        gap: 0.5rem;
        padding: 0 0.4rem 1rem;
        border-bottom: 1px solid #e9e9ee;
      }

      .pro-rail-avatar {
        width: 76px;
        height: 76px;
        font-size: 1.6rem;
        margin: 0;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        color: #ffffff;
        background: linear-gradient(160deg, #1b8a56 0%, #147347 100%);
        border: 3px solid #ffffff;
        box-shadow: 0 6px 18px rgba(20, 115, 71, 0.25);
        position: relative;
        flex-shrink: 0;
      }

      .pro-rail-avatar::after {
        content: '';
        position: absolute;
        width: 16px;
        height: 16px;
        bottom: 3px;
        right: 3px;
        background: ${user.is_active ? '#22c55e' : '#ef4444'};
        border: 2px solid white;
        border-radius: 50%;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
      }

      .pro-rail-name {
        font-size: 0.98rem;
        font-weight: 650;
        color: #1c1c1e;
        line-height: 1.25;
        letter-spacing: -0.01em;
        word-break: break-word;
      }

      .pro-rail-role {
        font-size: 0.74rem;
        font-weight: 500;
        color: #8e8e93;
        line-height: 1.3;
        word-break: break-word;
      }

      .pro-nav {
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
        padding: 0.75rem 0 0;
        flex: 1;
        min-height: 0;
        overflow-y: auto;
      }

      .pro-nav-item {
        position: relative;
        display: flex;
        align-items: center;
        gap: 0.65rem;
        width: 100%;
        padding: 0.62rem 0.75rem;
        border: none;
        background: transparent;
        border-radius: 8px;
        font-size: 0.8rem;
        font-weight: 500;
        color: #636366;
        cursor: pointer;
        text-align: left;
        outline: none;
        -webkit-tap-highlight-color: transparent;
        transition: background-color 0.18s ease, color 0.18s ease;
      }

      .pro-nav-item:hover:not(.active) {
        background: rgba(0, 0, 0, 0.04);
        color: #1c1c1e;
      }

      .pro-nav-item.active {
        background: rgba(20, 115, 71, 0.1);
        color: #0f5132;
        font-weight: 600;
        box-shadow: none;
      }

      .pro-nav-ico {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 22px;
        height: 22px;
        flex-shrink: 0;
        color: #aeaeb2;
        transition: color 0.18s ease;
      }

      .pro-nav-item:hover:not(.active) .pro-nav-ico {
        color: #636366;
      }

      .pro-nav-item.active .pro-nav-ico {
        color: #147347;
      }

      .pro-nav-ico svg {
        width: 18px;
        height: 18px;
      }

      .pro-rail-foot {
        padding-top: 0.85rem;
        margin-top: 0.5rem;
        border-top: 1px solid #e9e9ee;
      }

      .pro-rail-status {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.55rem 0.7rem;
        border-radius: 10px;
        font-size: 0.74rem;
        font-weight: 650;
        letter-spacing: 0.02em;
        text-transform: uppercase;
      }

      .pro-rail-status svg {
        width: 16px;
        height: 16px;
        flex-shrink: 0;
      }

      .pro-rail-status.is-active {
        background: #e7f7ee;
        color: #15803d;
      }

      .pro-rail-status.is-inactive {
        background: #fdecec;
        color: #c62828;
      }

      /* Right main panel */
      .pro-main {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
      }

      .pro-main-header {
        flex-shrink: 0;
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1rem;
        padding: 1.3rem 1.5rem 1rem;
        border-bottom: 1px solid #ececf1;
      }

      .pro-main-heading {
        min-width: 0;
      }

      .pro-main-title {
        font-size: 1.3rem;
        font-weight: 700;
        color: #1c1c1e;
        margin: 0 0 0.2rem;
        letter-spacing: -0.02em;
        line-height: 1.2;
      }

      .pro-main-sub {
        font-size: 0.8rem;
        color: #8e8e93;
        margin: 0;
        line-height: 1.35;
      }

      .pro-main-close {
        flex-shrink: 0;
        width: 34px;
        height: 34px;
        border-radius: 9px;
        border: 1px solid transparent;
        background: transparent;
        color: #636366;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background-color 0.18s ease, color 0.18s ease, border-color 0.18s ease;
      }

      .pro-main-close:hover {
        background: #f2f2f7;
        color: #1c1c1e;
        border-color: #e5e5ea;
      }

      .pro-main-close svg {
        width: 19px;
        height: 19px;
      }

      .pro-main-body {
        flex: 1;
        min-height: 0;
        overflow-y: auto;
        -webkit-overflow-scrolling: touch;
        padding: 1.25rem 1.5rem;
      }

      .pro-main-footer {
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        padding: 0.85rem 1.5rem;
        border-top: 1px solid #ececf1;
        background: #fbfbfd;
      }

      .pro-main-footer-actions {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        margin-left: auto;
      }

      .pro-main-footer .pro-save-hint {
        margin: 0;
      }

      /* General Info form fields */
      .pro-field-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.95rem 1.1rem;
      }

      .pro-field {
        display: block;
        min-width: 0;
      }

      .pro-field-input--readonly {
        background: #f2f2f7;
        color: #636366;
        cursor: default;
      }

      .pro-field-input--readonly:focus {
        border-color: #d1d1d6;
        box-shadow: none;
        background: #f2f2f7;
      }

      /* Organization details */
      .pro-org {
        margin-top: 1.5rem;
      }

      .pro-org-title {
        font-size: 1.02rem;
        font-weight: 700;
        color: #1c1c1e;
        letter-spacing: -0.01em;
        margin-bottom: 0.7rem;
      }

      .pro-org-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.7rem;
      }

      .pro-org-card {
        display: flex;
        align-items: flex-start;
        gap: 0.65rem;
        padding: 0.75rem 0.8rem;
        background: #f7f7fa;
        border: 1px solid #ececf1;
        border-radius: 12px;
      }

      .pro-org-ico {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 34px;
        height: 34px;
        border-radius: 10px;
        flex-shrink: 0;
        background: color-mix(in srgb, var(--icon-color, #147347) 14%, #ffffff);
        color: var(--icon-color, #147347);
      }

      .pro-org-ico svg {
        width: 18px;
        height: 18px;
      }

      .pro-org-text {
        min-width: 0;
      }

      .pro-org-label {
        font-size: 0.68rem;
        font-weight: 600;
        color: #8e8e93;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 0.15rem;
      }

      .pro-org-value {
        font-size: 0.88rem;
        font-weight: 650;
        color: #1c1c1e;
        line-height: 1.3;
        word-break: break-word;
      }

      .pro-org-hint {
        font-size: 0.7rem;
        color: #8e8e93;
        margin: 0.7rem 0 0;
        line-height: 1.4;
      }
      
      /* Hero Section */
      .pro-hero {
        position: relative;
        flex-shrink: 0;
        padding: 0.9rem 3.25rem 0.85rem 1.15rem;
        background: linear-gradient(180deg, #1a7a4d 0%, #145c3a 100%);
        border-radius: 0;
        margin: 0 -1rem;
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
        gap: 0.3rem;
        min-width: 0;
        flex: 1;
      }
      
      /* Rail avatar wins over legacy .pro-avatar hero styles */
      .pro-avatar.pro-rail-avatar {
        width: 76px;
        height: 76px;
        font-size: 1.6rem;
        margin: 0;
        background: linear-gradient(160deg, #1b8a56 0%, #147347 100%) !important;
        backdrop-filter: none;
        border: 3px solid #ffffff;
        box-shadow: 0 6px 18px rgba(20, 115, 71, 0.25);
        color: #ffffff;
      }

      .pro-avatar.pro-rail-avatar::after {
        width: 16px;
        height: 16px;
        bottom: 3px;
        right: 3px;
      }
      
      .pro-name {
        font-size: 1.08rem;
        font-weight: 650;
        color: white;
        margin: 0;
        letter-spacing: -0.02em;
        line-height: 1.2;
        text-align: left;
        word-break: break-word;
      }
      
      .pro-role-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        background: rgba(255,255,255,0.18);
        backdrop-filter: blur(10px);
        padding: 0.34rem 0.72rem;
        border-radius: 100px;
        font-size: 0.69rem;
        font-weight: 500;
        color: rgba(255,255,255,0.95);
        border: 1px solid rgba(255,255,255,0.22);
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
        gap: 0.35rem;
        padding: 0.4rem 0.7rem;
        background: #ececf1;
        border-bottom: 1px solid #d8d8de;
        margin: 0 -1rem;
        flex-shrink: 0;
      }
      
      .pro-tab-panels {
        padding: 0;
      }
      
      .pro-tab {
        flex: 1;
        padding: 0.5rem 0.72rem;
        border: none;
        background: transparent;
        font-size: 0.77rem;
        font-weight: 600;
        color: #636366;
        cursor: pointer;
        border-radius: 10px;
        transition: all 0.2s ease;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.35rem;
      }
      
      .pro-tab:hover {
        background: rgba(255,255,255,0.55);
        color: #1c1c1e;
      }
      
      .pro-tab.active {
        background: #ffffff;
        color: #1c1c1e;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px rgba(0,0,0,0.03);
      }
      
      .pro-tab svg {
        width: 14px;
        height: 14px;
      }
      
      /* Tab Content */
      .pro-tab-content {
        display: none;
        padding: 0;
        animation: fadeIn 0.3s ease;
      }
      
      .pro-tab-content.active {
        display: block;
      }
      
      @keyframes fadeIn {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
      }
      
      /* Info grids — two columns on wide profile sheet */
      .pro-info-list {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
      }

      .pro-info-list--grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.5rem;
      }

      .pro-profile-bottom {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0.5rem;
        align-items: start;
        margin-top: 0.65rem;
      }

      .pro-hr-record {
        margin-top: 0.65rem;
        padding-top: 0.65rem;
        border-top: 1px solid #d8d8de;
      }

      .pro-info-section-label {
        font-size: 0.63rem;
        font-weight: 700;
        color: #8e8e93;
        text-transform: uppercase;
        letter-spacing: 0.09em;
        margin-bottom: 0.2rem;
      }

      .pro-info-section-hint {
        font-size: 0.67rem;
        color: #8e8e93;
        margin: 0 0 0.5rem;
        line-height: 1.3;
      }
      
      .pro-info-item {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        padding: 0.58rem 0.65rem;
        background: #ffffff;
        border-radius: 12px;
        border: 1px solid #e5e5ea;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
        min-height: 0;
      }
      
      .pro-info-item:hover {
        border-color: #d1d1d6;
        box-shadow: 0 2px 6px rgba(16, 24, 40, 0.08);
      }
      
      .pro-info-icon {
        width: 30px;
        height: 30px;
        border-radius: 9px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: var(--icon-color, #147347);
        color: white;
        flex-shrink: 0;
        box-shadow: 0 2px 6px color-mix(in srgb, var(--icon-color, #147347) 35%, transparent);
      }

      .pro-info-icon svg {
        width: 17px;
        height: 17px;
      }
      
      .pro-info-content {
        flex: 1;
        min-width: 0;
      }
      
      .pro-info-label {
        font-size: 0.66rem;
        font-weight: 600;
        color: #8e8e93;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 0.12rem;
      }
      
      .pro-info-value {
        font-size: 0.84rem;
        font-weight: 600;
        color: #1c1c1e;
        word-break: break-word;
      }
      
      @media (max-width: 540px) {
        .pro-info-list--grid,
        .pro-profile-bottom,
        .pro-profile-edit-grid {
          grid-template-columns: 1fr;
        }
      }
      
      .pro-profile-edit-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: 0.45rem;
      }
      
      /* Module Access cards */
      .pro-mod-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.65rem;
      }

      .pro-mod-card {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.8rem 0.9rem;
        background: #ffffff;
        border: 1px solid #e5e5ea;
        border-radius: 14px;
        box-shadow: 0 1px 3px rgba(16,24,40,0.05);
        transition: box-shadow 0.18s ease, border-color 0.18s ease, transform 0.15s ease;
        cursor: default;
        min-width: 0;
      }

      .pro-mod-card:hover {
        box-shadow: 0 4px 12px rgba(16,24,40,0.1);
        border-color: #d1d1d6;
        transform: translateY(-1px);
      }

      .pro-mod-icon {
        width: 38px;
        height: 38px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
      }

      .pro-mod-icon svg {
        width: 20px;
        height: 20px;
      }

      .pro-mod-body {
        flex: 1;
        min-width: 0;
      }

      .pro-mod-name {
        font-size: 0.82rem;
        font-weight: 650;
        color: #1c1c1e;
        line-height: 1.2;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .pro-mod-desc {
        font-size: 0.68rem;
        color: #8e8e93;
        margin-top: 0.15rem;
        line-height: 1.3;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .pro-mod-check {
        flex-shrink: 0;
        opacity: 0.85;
      }

      .pro-no-access {
        color: #94a3b8;
        font-size: 0.82rem;
        font-style: italic;
        margin: 0;
      }
      
      /* Footer / Member Since */
      .pro-footer, .pro-member-since {
        text-align: center;
        padding: 0.62rem 0 0.22rem;
        margin-top: 0.58rem;
        font-size: 0.74rem;
        color: #8e8e93;
        border-top: 1px solid #d8d8de;
      }
      
      .pro-member-since strong {
        color: #1c1c1e;
      }

      .pro-profile-edit {
        margin: 0;
        padding: 0.7rem;
        background: #ffffff;
        border-radius: 12px;
        border: 1px solid #e5e5ea;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
      }

      .pro-section-title {
        font-size: 0.78rem;
        font-weight: 650;
        color: #1c1c1e;
        margin-bottom: 0.3rem;
      }

      .pro-section-desc {
        font-size: 0.68rem;
        color: #8e8e93;
        margin: 0 0 0.48rem;
      }

      .pro-field-label {
        display: block;
        margin-bottom: 0.22rem;
        font-size: 0.68rem;
        color: #8e8e93;
      }

      .pro-field-input {
        width: 100%;
        padding: 0.5rem 0.58rem;
        border: 1px solid #d1d1d6;
        border-radius: 9px;
        font-size: 0.84rem;
        box-sizing: border-box;
        background: #fbfbfd;
        color: #1c1c1e;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
      }

      .pro-field-input:focus {
        outline: none;
        border-color: #18794e;
        box-shadow: 0 0 0 3px rgba(24, 121, 78, 0.14);
        background: #ffffff;
      }

      .pro-save-btn {
        margin-top: 0.48rem;
        border-radius: 999px;
      }

      .pro-save-hint {
        font-size: 0.68rem;
        color: #8e8e93;
        margin: 0.38rem 0 0;
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

      .pro-security-icon svg {
        width: 20px;
        height: 20px;
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
        padding: 0.5rem 0.95rem;
        font-size: 0.78rem;
        font-weight: 600;
        border-radius: 10px;
        border: none;
        cursor: pointer;
        transition: transform 0.15s ease, box-shadow 0.2s ease, background-color 0.2s ease, border-color 0.2s ease;
      }
      
      .pro-btn-primary {
        background: linear-gradient(160deg, #1b8a56 0%, #147347 100%);
        color: white;
        box-shadow: 0 3px 8px rgba(20, 115, 71, 0.26);
      }
      
      .pro-btn-primary:hover {
        transform: translateY(-0.5px);
        box-shadow: 0 5px 12px rgba(20, 115, 71, 0.3);
      }
      
      .pro-btn-outline {
        background: white;
        color: #167d4f;
        border: 1px solid #a6d8bf;
      }
      
      .pro-btn-outline:hover {
        background: #f4fbf7;
      }
      
      .pro-btn-sm {
        padding: 0.375rem 0.75rem;
        font-size: 0.75rem;
      }
      
      .pro-btn-danger {
        background: #fff5f5;
        color: #c62828;
        border: 1px solid #fecaca;
      }
      
      .pro-btn-danger:hover {
        background: #feeaea;
        border-color: #dc2626;
      }
      
      .pro-btn-success {
        background: linear-gradient(160deg, #27ae60 0%, #1e9f58 100%);
        color: white;
        box-shadow: 0 3px 8px rgba(30, 159, 88, 0.28);
      }
      
      .pro-btn-success:hover {
        transform: translateY(-0.5px);
        box-shadow: 0 5px 12px rgba(30, 159, 88, 0.32);
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
        background: linear-gradient(135deg, #125435 0%, #1a7a4d 100%);
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 0.9rem;
      }

      .pro-sig-header-icon svg {
        width: 17px;
        height: 17px;
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
      
      /* Two-pane stacks below this width */
      @media (max-width: 720px) {
        .pro-shell {
          flex-direction: column;
        }
        .pro-rail {
          width: 100%;
          flex-shrink: 0;
          border-right: none;
          border-bottom: 1px solid #e5e5ea;
          padding: 1rem 1rem 0.75rem;
        }
        .pro-rail-head {
          flex-direction: row;
          align-items: center;
          text-align: left;
          gap: 0.75rem;
          padding: 0 0 0.75rem;
        }
        .pro-rail-avatar {
          width: 52px;
          height: 52px;
          font-size: 1.15rem;
          border-width: 2px;
        }
        .pro-rail-avatar::after {
          width: 13px;
          height: 13px;
        }
        .pro-nav {
          flex-direction: row;
          flex-wrap: nowrap;
          overflow-x: auto;
          gap: 0.35rem;
          padding: 0.6rem 0 0.1rem;
          -webkit-overflow-scrolling: touch;
          scrollbar-width: none;
        }
        .pro-nav::-webkit-scrollbar { display: none; }
        .pro-nav-item {
          width: auto;
          white-space: nowrap;
          padding: 0.5rem 0.75rem;
        }

        .pro-rail-foot { display: none; }
        .pro-main-body {
          padding: 1.1rem 1.15rem;
        }
        .pro-main-header { padding: 1.1rem 1.15rem 0.85rem; }
        .pro-main-title { font-size: 1.15rem; }
        .pro-main-footer { padding: 0.75rem 1.15rem; }
        .pro-field-grid,
        .pro-org-grid {
          grid-template-columns: 1fr;
        }
      }

      /* Mobile Responsive - Profile Modal (phones) */
      @media (max-width: 480px) {
        .pro-container { height: 100%; }
        .pro-shell {
          height: 100%;
          max-height: none;
        }
        .pro-sig-grid {
          grid-template-columns: 1fr;
        }
        
        .pro-tab-panels {
          padding: 0;
        }
        
        .pro-hero {
          margin: 0 -0.875rem;
          padding: 0.85rem 3rem 0.8rem 0.9rem;
        }

        .pro-hero-main {
          gap: 0.7rem;
        }
        
        .pro-avatar.pro-rail-avatar {
          width: 52px;
          height: 52px;
          font-size: 1.15rem;
        }
        
        .pro-avatar.pro-rail-avatar::after {
          width: 13px;
          height: 13px;
        }
        
        .pro-name {
          font-size: 1.15rem;
          line-height: 1.25;
        }
        
        .pro-role-badge {
          font-size: 0.68rem;
          padding: 0.35rem 0.75rem;
        }
        
        .pro-tabs {
          margin: 0 -0.875rem;
          padding: 0.55rem 0.45rem;
          gap: 0.35rem;
        }
        
        .pro-tab {
          flex: 1;
          min-width: 0;
          min-height: 44px;
          padding: 0.45rem 0.35rem;
          font-size: 0.7rem;
          gap: 0.3rem;
          border-radius: 10px;
          -webkit-tap-highlight-color: rgba(18, 84, 53, 0.12);
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
          align-items: flex-start;
          padding: 0.625rem 0.625rem;
          gap: 0.625rem;
        }
        
        .pro-info-icon {
          width: 36px;
          height: 36px;
          font-size: 0.95rem;
          border-radius: 8px;
          margin-top: 0.1rem;
        }
        
        .pro-info-label {
          font-size: 0.625rem;
        }
        
        .pro-info-value {
          font-size: 0.875rem;
          line-height: 1.35;
        }
        
        .pro-mod-grid {
          grid-template-columns: 1fr;
          gap: 0.5rem;
        }

        .pro-mod-card {
          padding: 0.7rem 0.75rem;
        }

        .pro-mod-icon {
          width: 34px;
          height: 34px;
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
        border-color: #125435;
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
        display: flex;
        justify-content: center;
      }

      .pro-sig-empty-icon svg {
        width: 26px;
        height: 26px;
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
        border-color: #125435;
        box-shadow: 0 0 0 3px rgba(18,84,53,0.1);
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
        text-align: left;
        padding: 0.85rem 0 0;
        margin-top: 1rem;
        color: #8e8e93;
        font-size: 0.75rem;
        border-top: 1px solid #ececf1;
      }
      
      .pro-member-since strong {
        color: #3a3a3c;
        font-weight: 650;
      }
      
    </style>
    
    <div class="pro-container">
      <div class="pro-shell">
        <!-- LEFT RAIL -->
        <aside class="pro-rail">
          <div class="pro-rail-head">
            <div class="pro-avatar pro-rail-avatar">${getInitials()}</div>
            <div class="pro-rail-name">${escapeHtml(user.full_name || user.username)}</div>
            <div class="pro-rail-role">${escapeHtml(user.job_designation || getRoleDisplay())}</div>
          </div>
          <nav class="pro-nav">
            <button class="pro-nav-item active" data-tab="profile" onclick="switchProfileTab('profile')">
              <span class="pro-nav-ico">${I.user}</span><span>General Info</span>
            </button>
            <button class="pro-nav-item" data-tab="security" onclick="switchProfileTab('security')">
              <span class="pro-nav-ico">${I.shield}</span><span>Security Settings</span>
            </button>
            <button class="pro-nav-item" data-tab="modules" onclick="switchProfileTab('modules')">
              <span class="pro-nav-ico">${I.grid}</span><span>Module Access</span>
            </button>
            <button class="pro-nav-item" data-tab="signature" onclick="switchProfileTab('signature')">
              <span class="pro-nav-ico">${I.pen}</span><span>Signature</span>
            </button>
          </nav>
          <div class="pro-rail-foot">
            <div class="pro-rail-status ${user.is_active ? 'is-active' : 'is-inactive'}">
              ${user.is_active ? I.check : I.warn}
              <span>${user.is_active ? 'Active Account' : 'Inactive Account'}</span>
            </div>
          </div>
        </aside>

        <!-- RIGHT MAIN -->
        <section class="pro-main">
          <header class="pro-main-header">
            <div class="pro-main-heading">
              <h2 class="pro-main-title" id="proMainTitle">General Information</h2>
              <p class="pro-main-sub" id="proMainSub">Manage your personal profile details and contact preferences.</p>
            </div>
            <button class="pro-main-close" onclick="closeProfileModal()" aria-label="Close">${I.close}</button>
          </header>

          <div class="pro-main-body">
            <!-- General Info Panel -->
            <div class="pro-tab-content active" data-content="profile">
              <div class="pro-field-grid">
                <label class="pro-field">
                  <span class="pro-field-label">Full Legal Name</span>
                  <input type="text" class="pro-field-input" id="profileManagedFullName" value="${escapeHtml(user.full_name || '')}" maxlength="120" autocomplete="name" />
                </label>
                <label class="pro-field">
                  <span class="pro-field-label">Joining Date</span>
                  <input type="date" class="pro-field-input" id="profileManagedJoined" value="${user.employment_start_date ? escapeHtml(String(user.employment_start_date).slice(0, 10)) : ''}" />
                </label>
                <label class="pro-field">
                  <span class="pro-field-label">Email Address</span>
                  <input type="text" class="pro-field-input pro-field-input--readonly" value="${escapeHtml(user.email || 'Not provided')}" readonly />
                </label>
                <label class="pro-field">
                  <span class="pro-field-label">Phone Number</span>
                  <input type="text" class="pro-field-input pro-field-input--readonly" value="${escapeHtml(user.phone || 'Not provided')}" readonly />
                </label>
              </div>

              <div class="pro-org">
                <div class="pro-org-title">Organization Details</div>
                <div class="pro-org-grid">
                  <div class="pro-org-card">
                    <span class="pro-org-ico" style="--icon-color:#6366f1">${I.briefcase}</span>
                    <div class="pro-org-text">
                      <div class="pro-org-label">Job Title</div>
                      <div class="pro-org-value">${hrJobTitle}</div>
                    </div>
                  </div>
                  <div class="pro-org-card">
                    <span class="pro-org-ico" style="--icon-color:#8b5cf6">${I.manager}</span>
                    <div class="pro-org-text">
                      <div class="pro-org-label">Reporting Manager</div>
                      <div class="pro-org-value">${reportingMgrDisp}</div>
                    </div>
                  </div>
                  <div class="pro-org-card">
                    <span class="pro-org-ico" style="--icon-color:#f59e0b">${I.leave}</span>
                    <div class="pro-org-text">
                      <div class="pro-org-label">Annual Leave (days)</div>
                      <div class="pro-org-value">${annualLeavesDisp}</div>
                    </div>
                  </div>
                  <div class="pro-org-card">
                    <span class="pro-org-ico" style="--icon-color:#f43f5e">${I.clipboard}</span>
                    <div class="pro-org-text">
                      <div class="pro-org-label">Other Leave (days)</div>
                      <div class="pro-org-value">${otherLeavesDisp}</div>
                    </div>
                  </div>
                </div>
                <p class="pro-org-hint">Job title, leave balances, and reporting manager are maintained by an administrator.</p>
              </div>

              <div class="pro-member-since">
                Member since <strong>${formatDate(user.created_at).replace(' (GST)', '').split(',')[0]}</strong>
              </div>
            </div>

            <!-- Security Panel -->
            <div class="pro-tab-content" data-content="security">
              <div class="pro-security-card ${user.password_changed ? 'success' : 'warning'}">
                <div class="pro-security-icon">${user.password_changed ? I.check : I.warn}</div>
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

              <div class="pro-info-list pro-info-list--grid">
                <div class="pro-info-item">
                  <div class="pro-info-icon" style="--icon-color:${user.is_active ? '#16a34a' : '#dc2626'}">${I.shield}</div>
                  <div class="pro-info-content">
                    <div class="pro-info-label">Account Status</div>
                    <div class="pro-info-value" style="color: ${user.is_active ? '#16a34a' : '#dc2626'}">
                      ${user.is_active ? 'Active' : 'Inactive'}
                    </div>
                  </div>
                </div>
                <div class="pro-info-item">
                  <div class="pro-info-icon" style="--icon-color:#f59e0b">${I.role}</div>
                  <div class="pro-info-content">
                    <div class="pro-info-label">Role</div>
                    <div class="pro-info-value">${escapeHtml(getRoleDisplay())}</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Module Access Panel -->
            <div class="pro-tab-content" data-content="modules">
              <div class="pro-mod-grid">
                ${moduleBadges}
              </div>
            </div>

            <!-- Signature Panel -->
            <div class="pro-tab-content" data-content="signature">
              <div class="pro-sig-section">
                <div class="pro-sig-header">
                  <div class="pro-sig-header-icon">${I.pen}</div>
                  <div class="pro-sig-header-text">
                    <h4>Default Signature</h4>
                    <p>Used for automatic form signing</p>
                  </div>
                </div>
                <div class="pro-sig-body">
                  <div class="pro-sig-grid">
                    <div class="pro-sig-preview" id="profileSigPreview" title="Click to draw signature">
                      <div class="pro-sig-empty" id="profileSigEmpty">
                        <div class="pro-sig-empty-icon">${I.pen}</div>
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
          </div><!-- /.pro-main-body -->

          <footer class="pro-main-footer" id="proMainFooter">
            <span id="profileManagedSaveHint" class="pro-save-hint"></span>
            <div class="pro-main-footer-actions">
              <button type="button" class="pro-btn pro-btn-outline" onclick="closeProfileModal()">Cancel</button>
              <button type="button" class="pro-btn pro-btn-primary" id="profileManagedSaveBtn">Save Changes</button>
            </div>
          </footer>
        </section>
      </div><!-- /.pro-shell -->
      
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
const PROFILE_PANEL_META = {
  profile: { title: 'General Information', sub: 'Manage your personal profile details and contact preferences.' },
  security: { title: 'Security Settings', sub: 'Review your account status and keep your password up to date.' },
  modules: { title: 'Module Access', sub: 'Workspaces and tools available to your account.' },
  signature: { title: 'Signature', sub: 'Set the default signature used to sign forms automatically.' }
};

window.switchProfileTab = function(tabName) {
  document.querySelectorAll('.pro-nav-item, .pro-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.tab === tabName);
  });
  document.querySelectorAll('.pro-tab-content').forEach(content => {
    content.classList.toggle('active', content.dataset.content === tabName);
  });

  const meta = PROFILE_PANEL_META[tabName];
  if (meta) {
    const titleEl = document.getElementById('proMainTitle');
    const subEl = document.getElementById('proMainSub');
    if (titleEl) titleEl.textContent = meta.title;
    if (subEl) subEl.textContent = meta.sub;
  }

  // Footer (Save Changes) only applies to the editable General Info panel
  const footer = document.getElementById('proMainFooter');
  if (footer) footer.style.display = (tabName === 'profile') ? '' : 'none';

  // Ensure the signature pad lays out correctly once its panel is visible
  if (tabName === 'signature') {
    setTimeout(() => { try { window.dispatchEvent(new Event('resize')); } catch (e) {} }, 60);
  }
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
    const cached = readCachedUser();
    if (cached) applyUserSession(cached);
    refreshCurrentUser(applyUserSession);
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
  } else if (isReviewHistoryPage || hasMainNav) {
    loadUserWelcome();
    runNavVisibility();
    if (document.getElementById('inspection-stats-grid')) {
      loadInspectionDashboardStats();
    }
  }

  if (document.getElementById('welcome-text')) {
    let navWelcomeResizeTimer;
    window.addEventListener('resize', function () {
      clearTimeout(navWelcomeResizeTimer);
      navWelcomeResizeTimer = setTimeout(function () {
        try {
          const userStr = localStorage.getItem('user');
          if (userStr) applyNavWelcome(JSON.parse(userStr));
        } catch (e) { /* ignore */ }
      }, 120);
    });
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
    document.body.classList.remove('mobile-menu-open');
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
    document.body.classList.add('mobile-menu-open');
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

  // Poll for new notifications (60s — avoids hitting global rate limits in dev)
  if (!window._injaazNotifPollTimer) {
    window._injaazNotifPollTimer = setInterval(loadNotificationCount, 60000);
  }
}

let _notifPollBackoffUntil = 0;

async function loadNotificationCount() {
  const badge = document.getElementById('notificationBadge');
  if (!badge) return;

  if (Date.now() < _notifPollBackoffUntil) return;

  try {
    const token = localStorage.getItem('access_token');
    if (!token) return;

    const response = await authenticatedFetch('/hr/api/notifications/unread-count');
    if (response.status === 429) {
      // Server rate limit — back off quietly (global default is often 100/hour)
      _notifPollBackoffUntil = Date.now() + 5 * 60 * 1000;
      return;
    }
    if (response.ok) {
      const data = await response.json();
      updateNotificationBadge(data.unread_count || 0);
      _notifPollBackoffUntil = 0;
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
