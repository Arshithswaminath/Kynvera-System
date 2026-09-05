/**
 * Default sign-off comments: "Signed & Verified — {FirstName}"
 * Optional profile notes append after a second em dash.
 */
(function (global) {
  'use strict';

  const SIGNED_VERIFIED = 'Signed & Verified';
  const SV_PHRASE_RE = /^Signed\s*(?:&|and)\s*Verified/i;
  const SV_BARE_RE = /^Signed\s*(?:&|and)\s*Verified\.?$/i;
  const SV_PREFIX_RE = /^Signed\s*(?:&|and)\s*Verified\s*[-—–]\s*([^\n—]+?)(?:\s*[—–]\s*([\s\S]*))?$/i;

  let userDefaultComment = '';
  let userFullName = '';
  let userUsername = '';

  function reviewerFirstName() {
    const full = (userFullName || '').trim();
    if (full) return full.split(/\s+/)[0];
    return (userUsername || 'Reviewer').trim();
  }

  function signedVerifiedPrefix() {
    return `${SIGNED_VERIFIED} — ${reviewerFirstName()}`;
  }

  function isBareSignedVerified(text) {
    return SV_BARE_RE.test(String(text || '').trim());
  }

  function isSignedVerifiedPhrase(text) {
    return SV_PHRASE_RE.test(String(text || '').trim());
  }

  function isRedundantSignedVerifiedChunk(text) {
    const s = String(text || '').trim();
    if (!s) return true;
    if (isBareSignedVerified(s)) return true;
    const m = s.match(SV_PREFIX_RE);
    if (m && !(m[2] || '').trim()) return true;
    return false;
  }

  function parseSignedVerifiedComment(text) {
    const trimmed = String(text || '').trim();
    const match = trimmed.match(SV_PREFIX_RE);
    if (!match) return { hasPrefix: false, name: '', suffix: trimmed };
    return {
      hasPrefix: true,
      name: (match[1] || '').trim(),
      suffix: (match[2] || '').trim(),
    };
  }

  function buildSignedVerifiedComment(name, extra) {
    const base = `${SIGNED_VERIFIED} — ${name || reviewerFirstName()}`;
    const note = String(extra || '').trim();
    if (!note || isRedundantSignedVerifiedChunk(note)) return base;
    return `${base} — ${note}`;
  }

  function resolveDefaultApprovalComment() {
    const custom = (userDefaultComment || '').trim();
    if (!custom || isBareSignedVerified(custom) || custom.toLowerCase() === 'approved') {
      return signedVerifiedPrefix();
    }
    if (isSignedVerifiedPhrase(custom)) {
      return ensureSignedVerifiedComment(custom);
    }
    return buildSignedVerifiedComment(reviewerFirstName(), custom);
  }

  function ensureSignedVerifiedComment(raw) {
    const name = reviewerFirstName();
    const parsed = parseSignedVerifiedComment(raw);
    if (parsed.hasPrefix) {
      return buildSignedVerifiedComment(name, parsed.suffix);
    }
    const body = String(raw || '').trim();
    if (!body || isBareSignedVerified(body) || isSignedVerifiedPhrase(body)) {
      return signedVerifiedPrefix();
    }
    return buildSignedVerifiedComment(name, body);
  }

  function setUserContext(user) {
    if (!user) return;
    userDefaultComment = user.default_comment || '';
    userFullName = user.full_name || '';
    userUsername = user.username || '';
  }

  function bindCommentField(el) {
    if (!el || el.dataset.signedVerifiedBound) return;
    el.dataset.signedVerifiedBound = '1';
    el.addEventListener('blur', () => {
      const normalized = ensureSignedVerifiedComment(el.value);
      if (normalized !== el.value) el.value = normalized;
    });
  }

  function bindApprovalCommentFields(root) {
    const scope = root || document;
    const getById = (id) => (scope.getElementById ? scope.getElementById(id) : document.getElementById(id));
    [
      'supervisorComments',
      'operationsManagerComments',
      'businessDevComments',
      'procurementComments',
      'generalManagerComments',
      'signoffModalComments',
      'rspComments',
    ].forEach((id) => bindCommentField(getById(id)));
    (scope.querySelectorAll ? scope.querySelectorAll('textarea[data-approval-comment]') : []).forEach(bindCommentField);
  }

  function normalizeCommentFields(root) {
    const scope = root || document;
    const getById = (id) => (scope.getElementById ? scope.getElementById(id) : document.getElementById(id));
    [
      'supervisorComments',
      'operationsManagerComments',
      'businessDevComments',
      'procurementComments',
      'generalManagerComments',
    ].forEach((id) => {
      const el = getById(id);
      if (el && el.value.trim()) el.value = ensureSignedVerifiedComment(el.value);
    });
  }

  const api = {
    SIGNED_VERIFIED,
    setUserContext,
    reviewerFirstName,
    signedVerifiedPrefix,
    resolveDefaultApprovalComment,
    ensureSignedVerifiedComment,
    bindApprovalCommentFields,
    bindCommentField,
    normalizeCommentFields,
  };

  global.KynveraApprovalComment = api;
  global.InjaazApprovalComment = api;
  global.resolveDefaultApprovalComment = resolveDefaultApprovalComment;
  global.ensureSignedVerifiedComment = ensureSignedVerifiedComment;
})(typeof window !== 'undefined' ? window : globalThis);
