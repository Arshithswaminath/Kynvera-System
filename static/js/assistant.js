/**
 * Injaaz Live Assistant widget (no-LLM v1)
 */
(function () {
  'use strict';

  var HIDDEN_PATHS = ['/', '/login', '/register', '/forgot-password', '/reset-password'];
  var MAX_HISTORY = 20;
  var DEFAULT_CHIPS = [
    'How many pending forms?',
    'My last leave',
    'Find a document',
    'Change my password',
  ];

  var root, fab, navBtn, panel, closeBtn, messagesEl, suggestionsEl, form, input, sendBtn;
  var isOpen = false;
  var isLoading = false;
  var greeted = false;

  function isAuthenticatedPage() {
    var path = (window.location.pathname || '').replace(/\/$/, '') || '/';
    if (HIDDEN_PATHS.indexOf(path) !== -1) return false;
    if (path === '/login') return false;
    return !!localStorage.getItem('access_token');
  }

  function escapeHtml(text) {
    if (!text) return '';
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function renderStatCard(card) {
    return (
      '<div class="injaaz-assistant-card injaaz-assistant-card--stat">' +
        '<span class="injaaz-assistant-card-label">' + escapeHtml(card.label || '') + '</span>' +
        '<span class="injaaz-assistant-card-value">' + escapeHtml(String(card.value || '')) + '</span>' +
      '</div>'
    );
  }

  function renderLeaveCard(card) {
    return (
      '<div class="injaaz-assistant-card">' +
        '<div class="injaaz-assistant-card-title">' + escapeHtml(card.leave_type || 'Leave') + '</div>' +
        '<div class="injaaz-assistant-card-meta">' +
          escapeHtml(card.start_date || '—') + ' → ' + escapeHtml(card.end_date || '—') +
          (card.total_days ? ' · ' + escapeHtml(String(card.total_days)) + ' days' : '') +
        '</div>' +
        '<div class="injaaz-assistant-card-meta">Status: ' + escapeHtml((card.status || '').replace(/_/g, ' ')) + '</div>' +
      '</div>'
    );
  }

  function renderDocumentCard(card) {
    var preview = card.preview_url ? (
      '<a class="injaaz-assistant-card-btn" href="' + escapeHtml(card.preview_url) + '" target="_blank" rel="noopener">Preview</a>'
    ) : '';
    var download = card.download_url ? (
      '<a class="injaaz-assistant-card-btn injaaz-assistant-card-btn--primary" href="' + escapeHtml(card.download_url) + '">Download</a>'
    ) : '';
    return (
      '<div class="injaaz-assistant-card">' +
        '<div class="injaaz-assistant-card-title">' + escapeHtml(card.title || 'Document') + '</div>' +
        '<div class="injaaz-assistant-card-meta">' +
          escapeHtml(card.category || '') +
          (card.updated_at ? ' · Updated ' + escapeHtml(card.updated_at) : '') +
        '</div>' +
        '<div class="injaaz-assistant-card-actions">' + preview + download + '</div>' +
      '</div>'
    );
  }

  function renderCards(cards) {
    if (!cards || !cards.length) return '';
    var html = cards.map(function (card) {
      if (card.type === 'stat') return renderStatCard(card);
      if (card.type === 'leave') return renderLeaveCard(card);
      if (card.type === 'document') return renderDocumentCard(card);
      return '';
    }).join('');
    return '<div class="injaaz-assistant-cards">' + html + '</div>';
  }

  function renderActions(actions) {
    if (!actions || !actions.length) return '';
    var html = actions.map(function (action) {
      var kind = action.kind || 'link';
      if (kind === 'profile_security') {
        return '<button type="button" class="injaaz-assistant-action" data-action-kind="profile_security">' +
          escapeHtml(action.label || 'Open Profile') + '</button>';
      }
      var href = action.href || '#';
      return '<a class="injaaz-assistant-action" href="' + escapeHtml(href) + '" data-action-kind="link">' +
        escapeHtml(action.label || 'Open') + '</a>';
    }).join('');
    return '<div class="injaaz-assistant-actions">' + html + '</div>';
  }

  function renderSources(sources) {
    if (!sources || !sources.length) return '';
    var text = sources.map(function (s) {
      return escapeHtml(s.title || s.source || '');
    }).filter(Boolean).join(' · ');
    return '<div class="injaaz-assistant-sources">Source: ' + text + '</div>';
  }

  function appendMessage(role, htmlContent) {
    var el = document.createElement('div');
    el.className = 'injaaz-assistant-msg injaaz-assistant-msg--' + role;
    el.innerHTML = htmlContent;
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return el;
  }

  function setSuggestions(chips) {
    suggestionsEl.innerHTML = '';
    var list = chips && chips.length ? chips : DEFAULT_CHIPS;
    list.forEach(function (chip) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'injaaz-assistant-chip';
      btn.textContent = chip;
      btn.addEventListener('click', function () {
        input.value = chip;
        sendMessage(chip);
      });
      suggestionsEl.appendChild(btn);
    });
  }

  function handleActionClick(e) {
    var btn = e.target.closest('[data-action-kind]');
    if (!btn) return;
    var kind = btn.getAttribute('data-action-kind');
    if (kind === 'profile_security') {
      e.preventDefault();
      if (typeof window.openProfileModal === 'function') {
        window.openProfileModal();
      }
      if (typeof window.switchProfileTab === 'function') {
        window.switchProfileTab('security');
      } else {
        setTimeout(function () {
          if (typeof window.switchProfileTab === 'function') {
            window.switchProfileTab('security');
          }
        }, 400);
      }
      return;
    }
  }

  function buildExtrasHtml(data) {
    return renderCards(data.cards) + renderActions(data.actions) + renderSources(data.sources);
  }

  function renderBotResponse(data) {
    var text = data.message || '';
    var extras = buildExtrasHtml(data);
    var html = escapeHtml(text) + extras;
    appendMessage('bot', html);
    setSuggestions(data.suggestions);
  }

  function setLoading(loading) {
    isLoading = loading;
    sendBtn.disabled = loading;
    input.disabled = loading;
  }

  async function sendMessage(text) {
    var message = (text || '').trim();
    if (!message || isLoading) return;

    appendMessage('user', escapeHtml(message));
    input.value = '';
    setLoading(true);
    var typingEl = appendMessage('typing', 'Thinking…');

    try {
      var fetchFn = window.authenticatedFetch || window.fetch;
      var response = await fetchFn('/api/assistant/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message }),
      });

      typingEl.remove();

      if (!response || !response.ok) {
        if (response && response.status === 401) {
          appendMessage('bot', 'Please log in to use the assistant.');
          return;
        }
        var errData = response ? await response.json().catch(function () { return {}; }) : {};
        appendMessage('bot', escapeHtml(errData.error || 'Something went wrong. Please try again.'));
        return;
      }

      var result = await response.json();
      var data = result.data || result;
      renderBotResponse(data);
      persistHistory(message, data);
    } catch (err) {
      typingEl.remove();
      appendMessage('bot', 'Unable to reach the assistant. Check your connection and try again.');
      console.error('Assistant error:', err);
    } finally {
      setLoading(false);
      input.focus();
    }
  }

  function persistHistory(userMsg, botData) {
    try {
      var raw = sessionStorage.getItem('injaaz_assistant_history');
      var history = raw ? JSON.parse(raw) : [];
      history.push({ user: userMsg, bot: botData });
      if (history.length > MAX_HISTORY) {
        history = history.slice(history.length - MAX_HISTORY);
      }
      sessionStorage.setItem('injaaz_assistant_history', JSON.stringify(history));
    } catch (e) { /* ignore */ }
  }

  function showWelcomeIfNeeded() {
    if (greeted) return;
    greeted = true;
    appendMessage(
      'bot',
      'Hi! Ask me anything about Injaaz — I\u2019m here to help.'
    );
    setSuggestions(DEFAULT_CHIPS);
  }

  function setTriggerExpanded(expanded) {
    if (navBtn) navBtn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    if (fab) fab.setAttribute('aria-expanded', expanded ? 'true' : 'false');
  }

  function focusTrigger() {
    var el = navBtn && navBtn.offsetParent !== null ? navBtn : fab;
    if (el) el.focus();
  }

  function togglePanel() {
    if (isOpen) closePanel();
    else openPanel();
  }

  function ensureBodyMount() {
    if (root && root.parentElement !== document.body) {
      document.body.appendChild(root);
    }
  }

  function openPanel() {
    ensureBodyMount();
    isOpen = true;
    root.classList.add('is-open');
    root.setAttribute('aria-hidden', 'false');
    setTriggerExpanded(true);
    showWelcomeIfNeeded();
    setTimeout(function () {
      try {
        input.focus({ preventScroll: true });
      } catch (e) {
        input.focus();
      }
    }, 200);
  }

  function closePanel() {
    isOpen = false;
    root.classList.remove('is-open');
    root.setAttribute('aria-hidden', 'true');
    setTriggerExpanded(false);
    focusTrigger();
  }

  function init() {
    root = document.getElementById('injaazAssistant');
    if (!root) return;

    ensureBodyMount();

    fab = document.getElementById('assistantFab');
    navBtn = document.getElementById('navAssistantBtn');
    panel = document.getElementById('assistantPanel');
    closeBtn = document.getElementById('assistantClose');
    messagesEl = document.getElementById('assistantMessages');
    suggestionsEl = document.getElementById('assistantSuggestions');
    form = document.getElementById('assistantForm');
    input = document.getElementById('assistantInput');
    sendBtn = document.getElementById('assistantSend');

    if (!isAuthenticatedPage()) {
      root.classList.add('is-hidden');
      if (navBtn) navBtn.classList.add('is-hidden');
      return;
    }

    if (navBtn) {
      root.classList.add('has-nav-trigger');
      navBtn.addEventListener('click', togglePanel);
    }

    if (fab) {
      fab.addEventListener('click', togglePanel);
    }

    closeBtn.addEventListener('click', closePanel);

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      sendMessage(input.value);
    });

    messagesEl.addEventListener('click', handleActionClick);

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isOpen) closePanel();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
