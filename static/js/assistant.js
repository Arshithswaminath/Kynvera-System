/**
 * Kynvera assistant widget — LLM agent with confirm-before-write.
 */
(function () {
  'use strict';

  var HIDDEN_PATHS = ['/', '/login', '/register', '/forgot-password', '/reset-password'];
  var MAX_HISTORY = 20;
  var DEFAULT_CHIPS = [
    'How many pending forms?',
    'My last leave',
    'Create a ticket draft',
    'Save a leave draft',
  ];

  var root, fab, navBtn, panel, closeBtn, messagesEl, suggestionsEl, form, input, sendBtn;
  var infoBtn, infoOverlay, infoCloseBtn, infoCard;
  var isOpen = false;
  var isLoading = false;
  var greeted = false;
  var infoOpen = false;

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

  function renderPendingAction(pending) {
    if (!pending || !pending.action_id) return '';
    var summary = pending.summary || {};
    var rows = Object.keys(summary).map(function (key) {
      var label = key.replace(/_/g, ' ');
      return (
        '<div class="injaaz-assistant-pending-row">' +
          '<span>' + escapeHtml(label) + '</span>' +
          '<strong>' + escapeHtml(String(summary[key] == null ? '—' : summary[key])) + '</strong>' +
        '</div>'
      );
    }).join('');
    var title = pending.action_type === 'leave_draft' ? 'Save leave draft' : 'Create ticket draft';
    return (
      '<div class="injaaz-assistant-card injaaz-assistant-pending" data-action-id="' +
        escapeHtml(String(pending.action_id)) + '">' +
        '<div class="injaaz-assistant-card-title">' + escapeHtml(title) + '</div>' +
        '<p class="injaaz-assistant-card-meta">Nothing is saved until you confirm.</p>' +
        (rows ? '<div class="injaaz-assistant-pending-rows">' + rows + '</div>' : '') +
        '<div class="injaaz-assistant-card-actions">' +
          '<button type="button" class="injaaz-assistant-card-btn injaaz-assistant-card-btn--primary" data-action-kind="confirm" data-action-id="' +
            escapeHtml(String(pending.action_id)) + '">Confirm</button>' +
          '<button type="button" class="injaaz-assistant-card-btn" data-action-kind="cancel" data-action-id="' +
            escapeHtml(String(pending.action_id)) + '">Cancel</button>' +
        '</div>' +
      '</div>'
    );
  }

  function renderComposerField(field) {
    var name = field.name || '';
    var label = field.label || name;
    var required = field.required ? ' required' : '';
    var value = field.value != null ? String(field.value) : '';
    var id = 'ac-' + name.replace(/[^a-z0-9_-]/gi, '');
    var labelHtml =
      '<label class="injaaz-assistant-composer-label" for="' + escapeHtml(id) + '">' +
        escapeHtml(label) + (field.required ? ' *' : '') +
      '</label>';
    var type = field.type || 'text';
    if (type === 'select') {
      var opts = (field.options || []).map(function (opt) {
        var v = typeof opt === 'string' ? opt : (opt.value || '');
        var lab = typeof opt === 'string' ? opt : (opt.label || v);
        var sel = String(value) === String(v) ? ' selected' : '';
        return '<option value="' + escapeHtml(v) + '"' + sel + '>' + escapeHtml(lab) + '</option>';
      }).join('');
      return (
        '<div class="injaaz-assistant-composer-field">' + labelHtml +
          '<select class="injaaz-assistant-composer-input" id="' + escapeHtml(id) +
            '" name="' + escapeHtml(name) + '"' + required + '>' + opts + '</select>' +
        '</div>'
      );
    }
    if (type === 'textarea') {
      return (
        '<div class="injaaz-assistant-composer-field">' + labelHtml +
          '<textarea class="injaaz-assistant-composer-input" id="' + escapeHtml(id) +
            '" name="' + escapeHtml(name) + '" rows="3"' + required + '>' +
            escapeHtml(value) + '</textarea>' +
        '</div>'
      );
    }
    var inputType = type === 'date' ? 'date' : 'text';
    return (
      '<div class="injaaz-assistant-composer-field">' + labelHtml +
        '<input class="injaaz-assistant-composer-input" id="' + escapeHtml(id) +
          '" name="' + escapeHtml(name) + '" type="' + inputType + '" value="' +
          escapeHtml(value) + '"' + required + '>' +
      '</div>'
    );
  }

  function renderComposer(composer) {
    if (!composer || !composer.type) return '';
    var fields = (composer.fields || []).map(renderComposerField).join('');
    return (
      '<form class="injaaz-assistant-card injaaz-assistant-composer" data-composer-type="' +
        escapeHtml(composer.type) + '">' +
        '<div class="injaaz-assistant-card-title">' + escapeHtml(composer.title || 'Complete details') + '</div>' +
        (composer.hint ? '<p class="injaaz-assistant-card-meta">' + escapeHtml(composer.hint) + '</p>' : '') +
        fields +
        '<div class="injaaz-assistant-card-actions">' +
          '<button type="submit" class="injaaz-assistant-card-btn injaaz-assistant-card-btn--primary">Continue</button>' +
        '</div>' +
      '</form>'
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
    var composerForm = e.target.closest('.injaaz-assistant-composer');
    if (composerForm && e.target.closest('button, input, select, textarea, label')) {
      return;
    }
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
    if (kind === 'confirm' || kind === 'cancel') {
      e.preventDefault();
      var actionId = btn.getAttribute('data-action-id');
      if (actionId) postPendingDecision(kind, actionId, btn);
    }
  }

  function collectComposer(formEl) {
    var payload = { type: formEl.getAttribute('data-composer-type') || '' };
    var fields = formEl.querySelectorAll('[name]');
    for (var i = 0; i < fields.length; i++) {
      var el = fields[i];
      if (!el.name) continue;
      payload[el.name] = el.value;
    }
    return payload;
  }

  function handleComposerSubmit(e) {
    var formEl = e.target.closest('.injaaz-assistant-composer');
    if (!formEl) return;
    e.preventDefault();
    sendMessage('Please use these details.', { composer: collectComposer(formEl) });
  }

  async function postPendingDecision(kind, actionId, btn) {
    if (isLoading) return;
    setLoading(true);
    if (btn) btn.disabled = true;
    var typingEl = appendMessage('typing', 'Working…');
    var path = kind === 'cancel' ? '/api/assistant/cancel' : '/api/assistant/confirm';
    try {
      var fetchFn = window.authenticatedFetch || window.fetch;
      var response = await fetchFn(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action_id: Number(actionId) }),
      });
      typingEl.remove();
      if (!response || !response.ok) {
        var errData = response ? await response.json().catch(function () { return {}; }) : {};
        appendMessage('bot', escapeHtml(errData.error || 'Could not complete that action.'));
        return;
      }
      var result = await response.json();
      var data = result.data || result;
      renderBotResponse(data);
    } catch (err) {
      typingEl.remove();
      appendMessage('bot', 'Unable to reach the assistant. Check your connection and try again.');
      console.error('Assistant confirm/cancel error:', err);
    } finally {
      setLoading(false);
      if (input) input.focus();
    }
  }

  function buildExtrasHtml(data) {
    return (
      renderCards(data.cards) +
      renderPendingAction(data.pending_action) +
      renderComposer(data.composer) +
      renderActions(data.actions) +
      renderSources(data.sources)
    );
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

  async function sendMessage(text, extra) {
    var message = (text || '').trim();
    extra = extra || {};
    if ((!message && !extra.composer) || isLoading) return;

    appendMessage('user', escapeHtml(message || 'Continue'));
    input.value = '';
    setLoading(true);
    var typingEl = appendMessage('typing', 'Thinking…');

    try {
      var fetchFn = window.authenticatedFetch || window.fetch;
      var body = { message: message || 'Please use these details.' };
      if (extra.composer) body.composer = extra.composer;
      var response = await fetchFn('/api/assistant/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
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
      'Hi! Ask me anything about Kynvera — I\u2019m here to help.'
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
    if (infoOverlay && infoOverlay.parentElement !== document.body) {
      document.body.appendChild(infoOverlay);
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
    closeInfo();
    isOpen = false;
    root.classList.remove('is-open');
    root.setAttribute('aria-hidden', 'true');
    setTriggerExpanded(false);
    focusTrigger();
  }

  function openInfo() {
    if (!infoOverlay) return;
    ensureBodyMount();
    infoOpen = true;
    infoOverlay.hidden = false;
    if (infoBtn) infoBtn.setAttribute('aria-expanded', 'true');
    setTimeout(function () {
      if (infoCard) {
        try { infoCard.focus({ preventScroll: true }); } catch (e) { infoCard.focus(); }
      }
    }, 50);
  }

  function closeInfo() {
    if (!infoOverlay || infoOverlay.hidden) {
      infoOpen = false;
      if (infoBtn) infoBtn.setAttribute('aria-expanded', 'false');
      return;
    }
    infoOpen = false;
    infoOverlay.hidden = true;
    if (infoBtn) {
      infoBtn.setAttribute('aria-expanded', 'false');
      infoBtn.focus();
    }
  }

  function init() {
    root = document.getElementById('injaazAssistant');
    if (!root) return;

    ensureBodyMount();

    fab = document.getElementById('assistantFab');
    navBtn = document.getElementById('navAssistantBtn');
    panel = document.getElementById('assistantPanel');
    closeBtn = document.getElementById('assistantClose');
    infoBtn = document.getElementById('assistantInfoBtn');
    infoOverlay = document.getElementById('assistantInfoOverlay');
    infoCloseBtn = document.getElementById('assistantInfoClose');
    infoCard = infoOverlay ? infoOverlay.querySelector('.injaaz-assistant-info-card') : null;
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

    if (infoBtn) {
      infoBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        if (infoOpen) closeInfo();
        else openInfo();
      });
    }
    if (infoCloseBtn) infoCloseBtn.addEventListener('click', closeInfo);
    if (infoOverlay) {
      infoOverlay.addEventListener('click', function (e) {
        if (e.target && e.target.hasAttribute('data-info-dismiss')) closeInfo();
      });
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      sendMessage(input.value);
    });

    messagesEl.addEventListener('click', handleActionClick);
    messagesEl.addEventListener('submit', handleComposerSubmit);

    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      if (infoOpen) {
        e.preventDefault();
        closeInfo();
        return;
      }
      if (isOpen) closePanel();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
