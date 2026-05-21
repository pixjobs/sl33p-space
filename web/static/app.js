// ───── Shared Utilities ─────
// This file must load first. It declares globals used by auth.js, chat.js, music.js, player.js, library.js.

let _authToken = null;

// ───── API Helper ─────

async function api(url, method, body) {
  method = method || 'GET';
  var opts = { method: method, headers: { 'Content-Type': 'application/json' } };
  if (_authToken) opts.headers['Authorization'] = 'Bearer ' + _authToken;
  if (body) opts.body = JSON.stringify(body);
  var res = await fetch(url, opts);
  if (res.status === 401) {
    var user = window.firebase && firebase.auth().currentUser;
    if (user) {
      try {
        var token = await user.getIdToken(true);
        _authToken = token;
        opts.headers['Authorization'] = 'Bearer ' + token;
        res = await fetch(url, opts);
      } catch (e) { /* refresh failed */ }
    }
    if (res.status === 401) {
      if (window.location.pathname === '/sleep') {
        return { error: 'session_expired' };
      }
      _signOutAndGoHome();
      return { error: 'Authentication required' };
    }
  }
  if (res.status === 403) {
    var tierErr = await res.json();
    showToast(tierErr.error || 'Generation not allowed — upgrade your plan', 'error');
    return { tier_error: true, ...tierErr };
  }
  if (res.status === 429) {
    return { quota_error: true, ...await res.json() };
  }
  if (res.status >= 500) {
    try { return await res.json(); } catch (_) {}
    return { error: 'Something went wrong. Please try again.' };
  }
  return res.json();
}

// ───── Toast Notifications ─────

function showToast(message, type, duration) {
  type = type || 'info';
  duration = duration || 4000;
  var container = document.getElementById('toast-container');
  if (!container) return;

  var toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.textContent = message;

  container.appendChild(toast);
  requestAnimationFrame(function() { toast.classList.add('toast-visible'); });

  setTimeout(function() {
    toast.classList.remove('toast-visible');
    toast.addEventListener('transitionend', function() { toast.remove(); });
  }, duration);
}

// ───── Markdown Renderer ─────

function _renderMd(text) {
  var s = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  s = s
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
  var lines = s.split('\n');
  var html = '', inList = false;
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    var bullet = line.match(/^\s*[-*]\s+(.+)/);
    if (bullet) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += '<li>' + bullet[1] + '</li>';
    } else {
      if (inList) { html += '</ul>'; inList = false; }
      if (line.trim()) html += '<p>' + line.trim() + '</p>';
    }
  }
  if (inList) html += '</ul>';
  return html;
}

// ───── Feedback Widget ─────

var _feedbackType = 'idea';

function toggleFeedbackWidget() {
  var w = document.getElementById('feedback-widget');
  if (w) w.classList.toggle('hidden');
}

function selectFeedbackType(btn) {
  _feedbackType = btn.dataset.type;
  document.querySelectorAll('.feedback-type-pills .pill').forEach(function(p) {
    p.classList.toggle('active', p === btn);
  });
}

async function submitGeneralFeedback() {
  var text = document.getElementById('feedback-text');
  var msg = (text && text.value || '').trim();
  if (!msg) return;
  await api('/api/feedback', 'POST', {
    type: _feedbackType,
    message: msg,
    context: { page: window.location.pathname }
  });
  text.value = '';
  toggleFeedbackWidget();
  showToast('Feedback sent — thank you!', 'success');
}
