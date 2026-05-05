/**
 * Global nav to-do — floating panel under main nav (no overlay), localStorage, optional reminders.
 */
(function () {
  var LS_KEY = 'injaaz_nav_todos_v2';
  var LS_LEGACY = 'injaaz_nav_todos_v1';
  var items = [];
  var tickTimer = null;

  function load() {
    try {
      var raw = localStorage.getItem(LS_KEY);
      if (!raw) {
        raw = localStorage.getItem(LS_LEGACY);
        if (raw) {
          try {
            var old = JSON.parse(raw);
            if (Array.isArray(old)) {
              items = old.map(function (t) {
                return {
                  id: t.id,
                  text: t.text,
                  done: !!t.done,
                  createdAt: t.createdAt || Date.now(),
                  remindAt: null,
                  notified: false
                };
              });
              save();
            }
          } catch (e2) {
            items = [];
          }
        } else {
          items = [];
        }
        return;
      }
      var parsed = JSON.parse(raw);
      items = Array.isArray(parsed) ? parsed : [];
      items.forEach(function (t) {
        if (t.remindAt == null) t.remindAt = null;
        if (typeof t.notified !== 'boolean') t.notified = false;
      });
    } catch (e) {
      items = [];
    }
  }

  function save() {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify(items));
    } catch (e) {
      /* quota */
    }
  }

  function uid() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function parseRemindInput() {
    var el = document.getElementById('todoRemindInput');
    if (!el || !el.value) return null;
    var ms = new Date(el.value).getTime();
    if (Number.isNaN(ms)) return null;
    return ms;
  }

  function formatReminderLine(ms) {
    if (ms == null || ms === '') return '';
    var now = Date.now();
    if (ms < now) return 'Overdue';
    var d = ms - now;
    var minutes = Math.floor(d / 60000);
    if (minutes < 1) return 'Soon';
    if (minutes < 60) return 'In ' + minutes + ' min';
    var hours = Math.floor(minutes / 60);
    if (hours < 48) return 'In ' + hours + ' h';
    return new Date(ms).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  }

  function updateBadge() {
    var badge = document.getElementById('todoNavBadge');
    if (!badge) return;
    var n = items.filter(function (t) {
      return !t.done;
    }).length;
    if (n > 0) {
      badge.style.display = 'flex';
      badge.textContent = n > 99 ? '99+' : String(n);
    } else {
      badge.style.display = 'none';
    }
  }

  function render() {
    var ul = document.getElementById('todoList');
    if (!ul) return;
    updateBadge();

    if (!items.length) {
      ul.innerHTML =
        '<li class="todo-empty-li"><span class="todo-empty">No tasks yet.</span></li>';
      return;
    }

    ul.innerHTML = items
      .map(function (t) {
        var checked = t.done ? ' checked' : '';
        var cls = t.done ? 'todo-item todo-item--done' : 'todo-item';
        var remindLine = '';
        if (t.remindAt) {
          var overdue = !t.done && t.remindAt < Date.now();
          remindLine =
            '<span class="todo-item-remind' +
            (overdue ? ' todo-item-remind--overdue' : '') +
            '" data-remind-ms="' +
            String(t.remindAt) +
            '">' +
            formatReminderLine(t.remindAt) +
            '</span>';
        }
        return (
          '<li class="' +
          cls +
          '" data-id="' +
          escapeHtml(t.id) +
          '">' +
          '<div class="todo-item-row">' +
          '<label class="todo-item-label">' +
          '<input type="checkbox" class="todo-item-check" data-id="' +
          escapeHtml(t.id) +
          '"' +
          checked +
          ' />' +
          '<span class="todo-item-text">' +
          escapeHtml(t.text) +
          '</span>' +
          '</label>' +
          (remindLine || '') +
          '<button type="button" class="todo-item-delete" data-id="' +
          escapeHtml(t.id) +
          '" title="Remove" aria-label="Remove task">×</button>' +
          '</div>' +
          '</li>'
        );
      })
      .join('');
    refreshReminderLabels();
  }

  function refreshReminderLabels() {
    document.querySelectorAll('.todo-item-remind[data-remind-ms]').forEach(function (el) {
      var ms = parseInt(el.getAttribute('data-remind-ms'), 10);
      if (Number.isNaN(ms)) return;
      el.textContent = formatReminderLine(ms);
      var li = el.closest('.todo-item');
      var done = li && li.classList.contains('todo-item--done');
      if (!done) {
        el.classList.toggle('todo-item-remind--overdue', ms < Date.now());
      } else {
        el.classList.remove('todo-item-remind--overdue');
      }
    });
  }

  function isPanelOpen() {
    var p = document.getElementById('todoPanel');
    return p && p.classList.contains('is-open');
  }

  function startTicks() {
    stopTicks();
    tickTimer = setInterval(function () {
      if (isPanelOpen()) refreshReminderLabels();
    }, 60000);
  }

  function stopTicks() {
    if (tickTimer) {
      clearInterval(tickTimer);
      tickTimer = null;
    }
  }

  function checkDueReminders() {
    var changed = false;
    items.forEach(function (t) {
      if (t.done || !t.remindAt || t.notified) return;
      if (Date.now() >= t.remindAt) {
        t.notified = true;
        changed = true;
        tryNotify(t.text);
      }
    });
    if (changed) save();
  }

  function tryNotify(body) {
    if (typeof Notification === 'undefined') return;
    if (Notification.permission === 'granted') {
      try {
        new Notification('Task reminder', {
          body: body || 'Reminder',
          icon: '/static/logo.png'
        });
      } catch (e) {
        /* ignore */
      }
    }
  }

  function maybeRequestNotificationPermission() {
    if (typeof Notification === 'undefined') return;
    if (Notification.permission !== 'default') return;
    Notification.requestPermission().catch(function () {});
  }

  function setExpanded(open) {
    var btn = document.getElementById('todoNavBtn');
    if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  function openTodoPanel() {
    var p = document.getElementById('todoPanel');
    if (!p) return;
    p.classList.add('is-open');
    p.setAttribute('aria-hidden', 'false');
    setExpanded(true);
    startTicks();
    checkDueReminders();
    var inp = document.getElementById('todoNewInput');
    if (inp) {
      setTimeout(function () {
        inp.focus();
      }, 50);
    }
  }

  function closeTodoPanel() {
    var p = document.getElementById('todoPanel');
    if (!p) return;
    p.classList.remove('is-open');
    p.setAttribute('aria-hidden', 'true');
    setExpanded(false);
    stopTicks();
  }

  function toggleTodoPanel() {
    var p = document.getElementById('todoPanel');
    if (!p) return;
    if (p.classList.contains('is-open')) {
      closeTodoPanel();
    } else {
      openTodoPanel();
    }
  }

  function addTask() {
    var input = document.getElementById('todoNewInput');
    var text = input && input.value ? input.value.trim() : '';
    if (!text) return;
    var remindAt = parseRemindInput();
    if (remindAt) maybeRequestNotificationPermission();
    var remindInput = document.getElementById('todoRemindInput');
    items.unshift({
      id: uid(),
      text: text,
      done: false,
      createdAt: Date.now(),
      remindAt: remindAt,
      notified: false
    });
    if (input) input.value = '';
    if (remindInput) remindInput.value = '';
    save();
    render();
  }

  document.addEventListener('DOMContentLoaded', function () {
    load();
    render();
    setExpanded(false);

    var btn = document.getElementById('todoNavBtn');
    if (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        toggleTodoPanel();
      });
    }

    var addBtn = document.getElementById('todoAddBtn');
    if (addBtn) addBtn.addEventListener('click', addTask);

    var input = document.getElementById('todoNewInput');
    if (input) {
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          addTask();
        }
      });
    }

    var clearBtn = document.getElementById('todoClearDone');
    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        items = items.filter(function (t) {
          return !t.done;
        });
        save();
        render();
      });
    }

    var ul = document.getElementById('todoList');
    if (ul) {
      ul.addEventListener('change', function (e) {
        var cb = e.target.closest('input.todo-item-check');
        if (!cb) return;
        var id = cb.getAttribute('data-id');
        for (var i = 0; i < items.length; i++) {
          if (items[i].id === id) {
            items[i].done = cb.checked;
            break;
          }
        }
        save();
        render();
      });
      ul.addEventListener('click', function (e) {
        var del = e.target.closest('.todo-item-delete');
        if (!del) return;
        var id = del.getAttribute('data-id');
        items = items.filter(function (x) {
          return x.id !== id;
        });
        save();
        render();
      });
    }

    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      var p = document.getElementById('todoPanel');
      if (p && p.classList.contains('is-open')) closeTodoPanel();
    });

    setInterval(checkDueReminders, 30000);
  });

  window.toggleTodoPanel = toggleTodoPanel;
  window.openTodoModal = openTodoPanel;
  window.closeTodoModal = closeTodoPanel;
  window.closeTodoPanel = closeTodoPanel;
})();
