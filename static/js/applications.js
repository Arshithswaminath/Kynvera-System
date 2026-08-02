/**
 * Kynvera /applications interactions: screenshot lightbox and inquiry form.
 * No dependencies; loaded with `defer` from templates/applications.html.
 * Nav, scroll-spy and the mobile drawer come from landing.js.
 */
(function () {
  'use strict';

  var FOCUSABLE = 'button:not([disabled]), a[href], input, select, textarea';

  function initLightbox() {
    var box = document.getElementById('l-lightbox');
    var galleries = Array.prototype.slice.call(document.querySelectorAll('.l-gallery'));
    if (!box || !galleries.length) return;

    var img = document.getElementById('l-lightbox-img');
    var titleEl = document.getElementById('l-lightbox-title');
    var captionEl = document.getElementById('l-lightbox-caption');
    var countEl = document.getElementById('l-lightbox-count');
    var prevBtn = document.getElementById('l-lightbox-prev');
    var nextBtn = document.getElementById('l-lightbox-next');
    var closeBtn = box.querySelector('.l-lightbox-close');

    var group = [];
    var index = 0;
    var opener = null;

    function shotFrom(button) {
      return {
        src: button.getAttribute('data-shot-src'),
        title: button.getAttribute('data-shot-title') || '',
        caption: button.getAttribute('data-shot-caption') || ''
      };
    }

    function preload(src) {
      if (!src) return;
      var pre = new Image();
      pre.src = src;
    }

    function show(next) {
      index = (next + group.length) % group.length;
      var shot = shotFrom(group[index]);

      img.src = shot.src;
      img.alt = shot.title;
      titleEl.textContent = shot.title;
      captionEl.textContent = shot.caption;
      countEl.textContent = index + 1 + ' / ' + group.length;

      var single = group.length < 2;
      prevBtn.hidden = single;
      nextBtn.hidden = single;
      countEl.hidden = single;

      if (!single) {
        preload(shotFrom(group[(index + 1) % group.length]).src);
        preload(shotFrom(group[(index - 1 + group.length) % group.length]).src);
      }
    }

    function open(button) {
      var gallery = button.closest('.l-gallery');
      group = Array.prototype.slice.call(gallery.querySelectorAll('.l-gcard'));
      opener = button;

      box.hidden = false;
      document.body.classList.add('is-lightbox-open');
      show(group.indexOf(button));
      closeBtn.focus();
    }

    function close() {
      box.hidden = true;
      document.body.classList.remove('is-lightbox-open');
      img.removeAttribute('src');
      if (opener) opener.focus();
      opener = null;
    }

    galleries.forEach(function (gallery) {
      gallery.addEventListener('click', function (event) {
        var card = event.target.closest('.l-gcard');
        if (card) open(card);
      });
    });

    box.addEventListener('click', function (event) {
      if (event.target.closest('[data-lightbox-close]')) close();
    });

    prevBtn.addEventListener('click', function () {
      show(index - 1);
    });

    nextBtn.addEventListener('click', function () {
      show(index + 1);
    });

    document.addEventListener('keydown', function (event) {
      if (box.hidden) return;

      if (event.key === 'Escape') {
        close();
      } else if (event.key === 'ArrowRight') {
        show(index + 1);
      } else if (event.key === 'ArrowLeft') {
        show(index - 1);
      } else if (event.key === 'Tab') {
        // Keep focus inside the dialog while it is open.
        var stops = Array.prototype.slice
          .call(box.querySelectorAll(FOCUSABLE))
          .filter(function (el) {
            return !el.hidden && el.offsetParent !== null;
          });
        if (!stops.length) return;

        var first = stops[0];
        var last = stops[stops.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    });
  }

  function initContactForm() {
    var form = document.getElementById('l-contact-form');
    if (!form) return;

    var note = document.getElementById('l-form-note');
    var mailbox = form.getAttribute('data-mailto');
    var defaultNote = note ? note.textContent : '';

    function value(name) {
      var field = form.elements[name];
      return field ? field.value.trim() : '';
    }

    function setNote(text, state) {
      if (!note) return;
      note.textContent = text;
      note.classList.toggle('is-error', state === 'error');
      note.classList.toggle('is-done', state === 'done');
    }

    function flag(name, invalid) {
      var field = form.elements[name];
      if (!field) return;
      if (invalid) {
        field.setAttribute('aria-invalid', 'true');
      } else {
        field.removeAttribute('aria-invalid');
      }
    }

    form.addEventListener('submit', function (event) {
      event.preventDefault();

      var name = value('name');
      var email = value('email');
      var emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email);

      flag('name', !name);
      flag('email', !emailOk);

      if (!name || !emailOk) {
        setNote('Add your name and a valid email so we can reply.', 'error');
        (name ? form.elements.email : form.elements.name).focus();
        return;
      }

      var company = value('company');
      var interest = value('interest');
      var lines = [
        'Name: ' + name,
        'Company: ' + (company || '—'),
        'Email: ' + email,
        'Phone: ' + (value('phone') || '—'),
        'Interested in: ' + interest,
        '',
        'Message:',
        value('message') || '—'
      ];

      var subject = 'Kynvera inquiry — ' + interest + (company ? ' — ' + company : '');
      window.location.href =
        'mailto:' + mailbox + '?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(lines.join('\n'));

      setNote('Opening your email app. If nothing happens, write to ' + mailbox + '.', 'done');
    });

    form.addEventListener('input', function (event) {
      if (event.target.getAttribute('aria-invalid')) {
        event.target.removeAttribute('aria-invalid');
        setNote(defaultNote, '');
      }
    });
  }

  function init() {
    initLightbox();
    initContactForm();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
