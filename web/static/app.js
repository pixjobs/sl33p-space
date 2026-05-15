let _authToken = null;

if (window.__firebaseConfig) {
  firebase.initializeApp(window.__firebaseConfig);

  firebase.auth().onAuthStateChanged(function(user) {
    var signInBtn = document.getElementById('sign-in-btn');
    var userInfo = document.getElementById('nav-user-info');
    var avatar = document.getElementById('nav-avatar');
    var username = document.getElementById('nav-username');

    if (user) {
      user.getIdToken().then(function(token) {
        _authToken = token;
        return fetch('/api/auth/session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: token })
        });
      }).then(function() {
        var tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        if (tz) api('/api/user/timezone', 'POST', { timezone: tz });

        var refCode = localStorage.getItem('sl33p_ref');
        if (refCode) {
          localStorage.removeItem('sl33p_ref');
          api('/api/user/redeem-referral', 'POST', { code: refCode }).then(function(res) {
            if (res && res.status === 'ok') showToast('Referral bonus: +1 credit!', 'success');
          });
        }

        if (window.location.pathname === '/') window.location.href = '/plan';
      });
      if (signInBtn) signInBtn.style.display = 'none';
      if (userInfo) userInfo.style.display = '';
      if (avatar) { avatar.src = user.photoURL || ''; avatar.style.display = user.photoURL ? '' : 'none'; }
      if (username) username.textContent = user.displayName || user.email || '';
    } else {
      _authToken = null;
      if (signInBtn) signInBtn.style.display = '';
      if (userInfo) userInfo.style.display = 'none';
    }
  });

  // Refresh token before expiry
  setInterval(function() {
    var user = firebase.auth().currentUser;
    if (user) user.getIdToken(true).then(function(token) { _authToken = token; });
  }, 10 * 60 * 1000);
}

function signInWithGoogle() {
  if (!window.__firebaseConfig) return;
  var provider = new firebase.auth.GoogleAuthProvider();
  firebase.auth().signInWithPopup(provider).catch(function(err) {
    showToast('Sign-in failed: ' + err.message, 'error');
  });
}

function signInWithEmail(email, password) {
  if (!window.__firebaseConfig) return;
  var errEl = document.getElementById('auth-error');
  if (errEl) { errEl.textContent = ''; errEl.style.display = 'none'; }
  firebase.auth().signInWithEmailAndPassword(email, password).catch(function(err) {
    var msg = err.code === 'auth/user-not-found' ? 'No account found with this email.'
            : err.code === 'auth/wrong-password' ? 'Incorrect password.'
            : err.code === 'auth/invalid-email' ? 'Invalid email address.'
            : err.code === 'auth/invalid-credential' ? 'Incorrect email or password.'
            : err.code === 'auth/too-many-requests' ? 'Too many attempts. Try again later.'
            : err.message;
    if (errEl) { errEl.textContent = msg; errEl.style.display = ''; }
  });
}

function signUpWithEmail(email, password, displayName) {
  if (!window.__firebaseConfig) return;
  var errEl = document.getElementById('auth-error');
  if (errEl) { errEl.textContent = ''; errEl.style.display = 'none'; }
  firebase.auth().createUserWithEmailAndPassword(email, password).then(function(cred) {
    if (displayName && cred.user) {
      return cred.user.updateProfile({ displayName: displayName });
    }
  }).catch(function(err) {
    var msg = err.code === 'auth/email-already-in-use' ? 'An account with this email already exists.'
            : err.code === 'auth/weak-password' ? 'Password must be at least 6 characters.'
            : err.code === 'auth/invalid-email' ? 'Invalid email address.'
            : err.message;
    if (errEl) { errEl.textContent = msg; errEl.style.display = ''; }
  });
}

function resetPassword(email) {
  if (!window.__firebaseConfig) return;
  var errEl = document.getElementById('auth-error');
  if (!email) {
    if (errEl) { errEl.textContent = 'Enter your email address first.'; errEl.style.display = ''; }
    return;
  }
  firebase.auth().sendPasswordResetEmail(email).then(function() {
    if (errEl) { errEl.textContent = 'Password reset email sent. Check your inbox.'; errEl.style.display = ''; errEl.style.color = 'rgba(52,211,153,0.8)'; }
  }).catch(function(err) {
    var msg = err.code === 'auth/user-not-found' ? 'No account found with this email.'
            : err.code === 'auth/invalid-email' ? 'Invalid email address.'
            : err.message;
    if (errEl) { errEl.textContent = msg; errEl.style.display = ''; errEl.style.color = ''; }
  });
}

function signOutUser() {
  if (!window.__firebaseConfig) return;
  fetch('/api/auth/signout', { method: 'POST' });
  firebase.auth().signOut();
}

// ───── API Helper ─────

async function api(url, method, body) {
  method = method || 'GET';
  var opts = { method: method, headers: { 'Content-Type': 'application/json' } };
  if (_authToken) opts.headers['Authorization'] = 'Bearer ' + _authToken;
  if (body) opts.body = JSON.stringify(body);
  var res = await fetch(url, opts);
  if (res.status === 401) {
    showToast('Authentication required. Please sign in.', 'error');
    return { error: 'Authentication required' };
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

// ───── Chat ─────

function _renderMd(text) {
  // Sanitize first: escape HTML entities to prevent XSS
  var s = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  // Then apply safe markdown transformations on escaped content
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

var _lastUserQuery = '';

function _addChatRow(container, text, role, opts) {
  opts = opts || {};
  var row = document.createElement('div');
  row.className = 'coach-row coach-' + role;
  var avatar = document.createElement('div');
  avatar.className = 'coach-avatar';
  avatar.textContent = role === 'agent' ? 'S' : 'Y';
  var bubble = document.createElement('div');
  bubble.className = 'coach-bubble' + (opts.thinking ? ' thinking' : '');
  if (opts.raw) {
    bubble.textContent = text;
  } else {
    // Content is safe: _renderMd escapes HTML entities before applying formatting
    bubble.innerHTML = _renderMd(text);  // nosemgrep: innerHTML-xss (input is entity-escaped)
  }
  row.appendChild(avatar);
  row.appendChild(bubble);

  if (role === 'agent' && !opts.thinking) {
    var fb = document.createElement('div');
    fb.className = 'chat-feedback';
    var up = document.createElement('button');
    up.className = 'chat-fb-btn';
    up.textContent = '👍';
    up.title = 'Helpful';
    var down = document.createElement('button');
    down.className = 'chat-fb-btn';
    down.textContent = '👎';
    down.title = 'Not helpful';
    var query = _lastUserQuery;
    function doFb(type) {
      api('/api/feedback', 'POST', {
        type: type,
        context: { chat_response: text.substring(0, 500), user_query: query }
      });
      fb.textContent = 'Thanks';
      fb.classList.add('chat-fb-done');
    }
    up.onclick = function() { doFb('thumbs_up'); };
    down.onclick = function() { doFb('thumbs_down'); };
    fb.appendChild(up);
    fb.appendChild(down);
    row.appendChild(fb);
  }

  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
  return { row: row, bubble: bubble };
}

function sendChatMsg(msg) {
  var input = document.getElementById('chat-input');
  if (input) { input.value = msg; }
  if (input && input.form) input.form.dispatchEvent(new Event('submit', { cancelable: true }));
}

async function sendChat(e) {
  e.preventDefault();
  var input = document.getElementById('chat-input');
  var msg = input.value.trim();
  if (!msg) return;

  _lastUserQuery = msg;
  var messages = document.getElementById('chat-messages');
  _addChatRow(messages, msg, 'user', { raw: true });
  input.value = '';

  var quick = document.getElementById('coach-quick');
  if (quick) quick.style.display = 'none';

  var ref = _addChatRow(messages, 'Thinking...', 'agent', { raw: true, thinking: true });

  try {
    var data = await api('/api/chat', 'POST', { message: msg });
    if (data.quota_error) {
      ref.bubble.classList.remove('thinking');
      ref.bubble.textContent = data.error || 'Daily chat limit reached. Sleep longer to earn more!';
      _updateChatCounter(0);
      return;
    }
    var resp = data.response || data.error || 'No response';
    ref.bubble.classList.remove('thinking');
    // Response from our own API, entity-escaped in _renderMd before formatting
    ref.bubble.innerHTML = _renderMd(resp);  // nosemgrep: innerHTML-xss (input is entity-escaped)
    messages.scrollTop = messages.scrollHeight;

    if (data.remaining !== undefined) _updateChatCounter(data.remaining);

    if (resp.includes('/sleep?')) {
      var match = resp.match(/(\/sleep\?[^\s"']+)/);
      if (match) {
        var linkRow = _addChatRow(messages, '', 'agent', { raw: true });
        var a = document.createElement('a');
        a.href = match[1];
        a.textContent = 'Start session →';
        a.style.color = '#a78bfa';
        a.style.textDecoration = 'underline';
        linkRow.bubble.textContent = '';
        linkRow.bubble.appendChild(a);
      }
    }
  } catch (err) {
    ref.bubble.classList.remove('thinking');
    ref.bubble.textContent = 'Error: ' + err.message;
  }
}

function _updateChatCounter(remaining) {
  var el = document.getElementById('chat-remaining');
  if (!el) {
    var form = document.querySelector('.agent-chat-input');
    if (!form) return;
    el = document.createElement('div');
    el.id = 'chat-remaining';
    el.className = 'chat-remaining';
    form.appendChild(el);
  }
  if (remaining > 20) { el.style.display = 'none'; return; }
  el.style.display = '';
  el.textContent = remaining + ' left today';
  if (remaining <= 3) el.classList.add('chat-remaining-low');
  else el.classList.remove('chat-remaining-low');
}

// ───── Music Generation ─────

function _createTrackRow(track) {
  var row = document.createElement('div');
  row.className = 'track-row';
  row.dataset.id = track.id;
  row.dataset.src = '/media/music/' + track.filename;
  row.dataset.title = track.title;
  row.dataset.path = track.path;
  row.dataset.prompt = track.prompt || '';

  // play button
  var playBtn = document.createElement('button');
  playBtn.className = 'track-play-btn';
  playBtn.title = 'Play';
  playBtn.addEventListener('click', function() { playTrack(row); });
  playBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor" style="width:14px;height:14px"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
  row.appendChild(playBtn);

  // track info
  var info = document.createElement('div');
  info.className = 'track-info';
  var titleSpan = document.createElement('span');
  titleSpan.className = 'track-title';
  titleSpan.textContent = track.title;
  var metaSpan = document.createElement('span');
  metaSpan.className = 'track-meta';
  metaSpan.textContent = (track.size_kb || 0) + ' KB';
  info.appendChild(titleSpan);
  info.appendChild(metaSpan);
  row.appendChild(info);

  // action buttons
  var actions = document.createElement('div');
  actions.className = 'track-actions';

  function makeActionBtn(title, svg, handler, danger) {
    var b = document.createElement('button');
    b.className = 'track-action-btn' + (danger ? ' track-action-danger' : '');
    b.title = title;
    b.innerHTML = svg;
    b.addEventListener('click', handler);
    return b;
  }

  actions.appendChild(makeActionBtn('Add to queue',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:15px;height:15px"><path d="M12 5v14M5 12h14"/></svg>',
    function() { addToQueue(row); }));

  actions.appendChild(makeActionBtn('Variation',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:15px;height:15px"><path d="M12 2l1.09 3.26L16.18 6l-2.54 2.17L14.36 12 12 10.18 9.64 12l.72-3.83L7.82 6l3.09-.74z"/></svg>',
    function() { suggestVariation(row.dataset.prompt); }));

  actions.appendChild(makeActionBtn('Archive',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:15px;height:15px"><path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4"/></svg>',
    function() { archiveTrack(track.id); }));

  actions.appendChild(makeActionBtn('Delete',
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:15px;height:15px"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>',
    function() { deleteTrack(track.id, track.title); }, true));

  row.appendChild(actions);
  return row;
}

async function _refreshTrackList() {
  var tracks = await api('/api/music/library');
  if (!Array.isArray(tracks)) return;

  var list = document.getElementById('track-list');
  if (list) {
    list.textContent = '';
    if (tracks.length === 0) {
      var empty = document.createElement('div');
      empty.className = 'empty';
      var p = document.createElement('p');
      p.textContent = 'No tracks yet. Generate one above.';
      empty.appendChild(p);
      list.appendChild(empty);
    } else {
      tracks.forEach(function(track) {
        list.appendChild(_createTrackRow(track));
      });
    }
  }

  var picker = document.getElementById('track-picker');
  if (picker) {
    picker.textContent = '';
    tracks.forEach(function(track) {
      var btn = document.createElement('button');
      btn.className = 'track-card';
      btn.dataset.id = track.id;
      btn.dataset.src = '/media/music/' + track.filename;
      btn.dataset.title = track.title;
      btn.addEventListener('click', function() {
        if (typeof selectTrackCard === 'function') selectTrackCard(btn);
      });
      var title = document.createElement('span');
      title.className = 'track-card-title';
      title.textContent = track.title;
      var meta = document.createElement('span');
      meta.className = 'track-card-meta';
      meta.textContent = (track.size_kb || 0) + ' KB';
      btn.appendChild(title);
      btn.appendChild(meta);
      picker.appendChild(btn);
    });
  }

  var strip = document.getElementById('channel-strip');
  if (strip) {
    strip.textContent = '';
    tracks.forEach(function(track) {
      var card = document.createElement('button');
      card.className = 'channel-card';
      card.dataset.id = track.id;
      card.dataset.src = '/media/music/' + track.filename;
      card.dataset.title = track.title;
      card.addEventListener('click', function() {
        if (typeof selectChannel === 'function') selectChannel(card);
      });
      var name = document.createElement('div');
      name.className = 'channel-name';
      name.textContent = track.title;
      var meta = document.createElement('div');
      meta.className = 'channel-meta';
      meta.textContent = (track.size_kb || 0) + ' KB';
      card.appendChild(name);
      card.appendChild(meta);
      strip.appendChild(card);
    });
  }

  var trackStrip = document.getElementById('track-strip');
  if (trackStrip) {
    trackStrip.textContent = '';
    if (tracks.length === 0) {
      var emptyMsg = document.createElement('span');
      emptyMsg.className = 'col-span-2 text-xs text-white/30 py-2';
      emptyMsg.textContent = 'No tracks yet — generate one below';
      trackStrip.appendChild(emptyMsg);
    } else {
      tracks.forEach(function(track) {
        var energy = track.energy_level || 'low';
        var chip = document.createElement('button');
        chip.className = 'track-chip px-3 py-2.5 bg-transparent border border-border rounded-xl cursor-pointer transition-all text-left hover:border-border-hover hover:bg-surface-hover group';
        chip.dataset.id = track.id;
        chip.dataset.src = track.src || ('/media/music/' + track.filename);
        chip.dataset.title = track.title;
        chip.dataset.moodTags = (track.mood_tags || []).join(',');
        chip.dataset.energy = energy;
        chip.addEventListener('click', function() {
          if (typeof pickTrack === 'function') pickTrack(chip);
        });
        var header = document.createElement('div');
        header.className = 'flex items-center gap-1.5 mb-0.5';
        var dot = document.createElement('span');
        dot.className = 'energy-dot e-' + energy;
        var eLbl = document.createElement('span');
        eLbl.className = 'text-[0.55rem] text-white/25 uppercase tracking-wider';
        eLbl.textContent = energy;
        header.appendChild(dot);
        header.appendChild(eLbl);
        var t = document.createElement('span');
        t.className = 'block text-[0.75rem] font-medium text-white/80 truncate';
        t.textContent = track.title;
        chip.appendChild(header);
        chip.appendChild(t);
        if (track.mood_tags && track.mood_tags.length) {
          var m = document.createElement('span');
          m.className = 'block text-[0.5rem] text-white/20 mt-0.5 truncate';
          m.textContent = track.mood_tags.join(' · ');
          chip.appendChild(m);
        }
        trackStrip.appendChild(chip);
      });
    }
  }

  var countEl = document.querySelector('.track-count');
  if (countEl) countEl.textContent = tracks.length + ' track' + (tracks.length !== 1 ? 's' : '');
}

async function generateMusic(prompt, title) {
  var overlay = document.getElementById('gen-loading');
  if (overlay) overlay.classList.add('active');
  try {
    var res = await api('/api/music/generate', 'POST', { prompt: prompt, title: title });
    if (res.error) {
      showToast(res.error, 'error');
      if (overlay) overlay.classList.remove('active');
      return;
    }
    if (res.job_id) {
      showToast('Generating your track — this takes about a minute...', 'info', 15000);
      _pollJob(res.job_id, overlay);
      return;
    }
    showToast('Track ready: ' + (res.title || 'New track'), 'success');
    await _refreshTrackList();
    if (overlay) overlay.classList.remove('active');
  } catch (e) {
    showToast('Generation failed: ' + e.message, 'error');
    if (overlay) overlay.classList.remove('active');
  }
}

async function _pollJob(jobId, overlay) {
  for (var i = 0; i < 60; i++) {
    await new Promise(function(r) { setTimeout(r, 5000); });
    try {
      var job = await api('/api/music/job/' + jobId);
      if (job.status === 'complete') {
        var t = (job.result || {}).title || 'New track';
        showToast('Track created: ' + t, 'success');
        await _refreshTrackList();
        if (overlay) overlay.classList.remove('active');
        return;
      }
      if (job.status === 'failed') {
        showToast((job.result || {}).error || 'Generation failed', 'error');
        if (overlay) overlay.classList.remove('active');
        return;
      }
    } catch (e) { /* keep polling */ }
  }
  showToast('Generation is taking longer than expected. Check your library later.', 'info');
  if (overlay) overlay.classList.remove('active');
}

function generateFromPreset(name, prompt) {
  generateMusic(prompt, name);
}

async function generateCustom(e) {
  e.preventDefault();
  var input = document.getElementById('custom-prompt');
  var prompt = input.value.trim();
  if (!prompt) return;
  generateMusic(prompt, '');
}

// ───── Inspire & Variations ─────

async function inspireMe() {
  var btn = document.getElementById('inspire-btn') || document.getElementById('btn-inspire');
  var grid = document.getElementById('suggest-grid');
  if (!grid) return;

  if (btn) { btn.disabled = true; btn.classList.add('loading'); }
  grid.replaceChildren();

  try {
    var suggestions = await api('/api/music/suggest');
    if (!Array.isArray(suggestions) || suggestions.length === 0) {
      if (btn) { btn.disabled = false; btn.classList.remove('loading'); }
      return;
    }

    suggestions.forEach(function(s) {
      var card = document.createElement('button');
      card.className = 'suggest-card';
      card.addEventListener('click', function() { generateMusic(s.prompt, s.title); });

      var title = document.createElement('span');
      title.className = 'suggest-title';
      title.textContent = s.title;

      var prompt = document.createElement('span');
      prompt.className = 'suggest-prompt';
      prompt.textContent = s.prompt;

      card.appendChild(title);
      card.appendChild(prompt);
      grid.appendChild(card);
    });
  } catch (e) {
    // silent
  }
  if (btn) { btn.disabled = false; btn.classList.remove('loading'); }
}

async function suggestVariation(originalPrompt) {
  if (!originalPrompt) return;
  var details = document.getElementById('custom-details');
  var textarea = document.getElementById('custom-prompt');
  if (!details || !textarea) return;

  details.open = true;
  textarea.value = 'Generating variation...';
  textarea.disabled = true;

  try {
    var result = await api('/api/music/suggest-variation', 'POST', { prompt: originalPrompt });
    if (result.prompt) {
      textarea.value = result.prompt;
    } else {
      textarea.value = originalPrompt;
    }
  } catch (e) {
    textarea.value = originalPrompt;
  }
  textarea.disabled = false;
  textarea.focus();
  details.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// ───── Player & Queue ─────

var queue = [];
var queueIndex = -1;

function _audio() { return document.getElementById('player-audio'); }

function _formatTime(s) {
  if (!s || isNaN(s)) return '0:00';
  var m = Math.floor(s / 60);
  var sec = Math.floor(s % 60);
  return m + ':' + (sec < 10 ? '0' : '') + sec;
}

function _updatePlayerUI() {
  var audio = _audio();
  if (!audio) return;
  var player = document.getElementById('player');
  var titleEl = document.getElementById('player-title');
  var icon = document.getElementById('player-play-icon');
  var current = queueIndex >= 0 && queueIndex < queue.length ? queue[queueIndex] : null;

  if (current) {
    titleEl.textContent = current.title;
    player.classList.add('has-track');
  } else {
    titleEl.textContent = 'No track selected';
    player.classList.remove('has-track');
  }

  icon.replaceChildren();
  if (audio.paused) {
    var poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('points', '5 3 19 12 5 21 5 3');
    icon.appendChild(poly);
  } else {
    var r1 = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    r1.setAttribute('x','6'); r1.setAttribute('y','4'); r1.setAttribute('width','4'); r1.setAttribute('height','16');
    var r2 = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    r2.setAttribute('x','14'); r2.setAttribute('y','4'); r2.setAttribute('width','4'); r2.setAttribute('height','16');
    icon.appendChild(r1);
    icon.appendChild(r2);
  }

  document.querySelectorAll('.track-row').forEach(function(r) { r.classList.remove('active'); });
  if (current) {
    var row = document.querySelector('.track-row[data-src="' + current.src + '"]');
    if (row) row.classList.add('active');
  }

  _renderQueue();
}

function _renderQueue() {
  var section = document.getElementById('queue-section');
  var list = document.getElementById('queue-list');
  if (!section || !list) return;

  var upcoming = queue.slice(queueIndex + 1);
  if (upcoming.length === 0) {
    section.style.display = 'none';
    return;
  }
  section.style.display = '';
  list.replaceChildren();
  upcoming.forEach(function(t, i) {
    var item = document.createElement('div');
    item.className = 'queue-item';

    var num = document.createElement('span');
    num.className = 'queue-num';
    num.textContent = i + 1;

    var title = document.createElement('span');
    title.className = 'queue-item-title';
    title.textContent = t.title;

    var btn = document.createElement('button');
    btn.className = 'queue-remove';
    btn.textContent = '×';
    var removeIdx = queueIndex + 1 + i;
    btn.addEventListener('click', function() { removeFromQueue(removeIdx); });

    item.appendChild(num);
    item.appendChild(title);
    item.appendChild(btn);
    list.appendChild(item);
  });
}

function playTrack(row) {
  var src = row.dataset.src;
  var title = row.dataset.title;
  var path = row.dataset.path;

  var existing = queue.findIndex(function(t) { return t.src === src; });
  if (existing >= 0) {
    queueIndex = existing;
  } else {
    queue.push({ src: src, title: title, path: path });
    queueIndex = queue.length - 1;
  }
  _loadAndPlay();
}

function _loadAndPlay() {
  var audio = _audio();
  if (!audio || queueIndex < 0 || queueIndex >= queue.length) return;
  var track = queue[queueIndex];
  audio.src = track.src;
  var volSlider = document.getElementById('player-volume');
  if (volSlider) audio.volume = parseInt(volSlider.value) / 100;
  audio.play();
  _initVisualizer();
  _updatePlayerUI();
}

function setPlayerVolume(val) {
  var audio = _audio();
  if (audio) audio.volume = parseInt(val) / 100;
}

function playerToggle() {
  var audio = _audio();
  if (!audio) return;
  if (audio.src && !audio.paused) {
    audio.pause();
  } else if (audio.src) {
    audio.play();
    _initVisualizer();
  } else if (queue.length > 0) {
    queueIndex = 0;
    _loadAndPlay();
  }
  _updatePlayerUI();
}

function playerNext() {
  if (queueIndex < queue.length - 1) {
    queueIndex++;
    _loadAndPlay();
  }
}

function playerPrev() {
  var audio = _audio();
  if (audio && audio.currentTime > 3) {
    audio.currentTime = 0;
    return;
  }
  if (queueIndex > 0) {
    queueIndex--;
    _loadAndPlay();
  }
}

function playerSeek(val) {
  var audio = _audio();
  if (audio && audio.duration) {
    audio.currentTime = (val / 100) * audio.duration;
  }
}

function addToQueue(row) {
  var src = row.dataset.src;
  var title = row.dataset.title;
  var path = row.dataset.path;
  if (queue.some(function(t) { return t.src === src; })) {
    showToast('Already in queue', 'info');
    return;
  }
  queue.push({ src: src, title: title, path: path });
  if (queue.length === 1) {
    queueIndex = 0;
    _loadAndPlay();
  }
  _renderQueue();
  showToast('Added to queue', 'info');
}

function removeFromQueue(idx) {
  if (idx <= queueIndex) queueIndex--;
  queue.splice(idx, 1);
  _renderQueue();
}

function clearQueue() {
  var current = queueIndex >= 0 ? queue[queueIndex] : null;
  queue.length = 0;
  if (current) {
    queue.push(current);
    queueIndex = 0;
  } else {
    queueIndex = -1;
  }
  _renderQueue();
}

// Player time/progress
(function initPlayer() {
  var audio = document.getElementById('player-audio');
  if (!audio) return;

  audio.addEventListener('timeupdate', function() {
    var seek = document.getElementById('player-seek');
    var cur = document.getElementById('player-current');
    var dur = document.getElementById('player-duration');
    if (seek && audio.duration) seek.value = (audio.currentTime / audio.duration) * 100;
    if (cur) cur.textContent = _formatTime(audio.currentTime);
    if (dur) dur.textContent = _formatTime(audio.duration);
  });

  audio.addEventListener('ended', function() {
    if (queueIndex < queue.length - 1) {
      playerNext();
    } else {
      _updatePlayerUI();
    }
  });

  audio.addEventListener('pause', _updatePlayerUI);
  audio.addEventListener('play', _updatePlayerUI);
})();

// ───── Audio Visualizer ─────

var _vizCtx = null;
var _vizAnalyser = null;

function _initVisualizer() {
  var canvas = document.getElementById('visualizer');
  var audio = _audio();
  if (!canvas || !audio || _vizCtx) return;

  try {
    _vizCtx = new (window.AudioContext || window.webkitAudioContext)();
    var source = _vizCtx.createMediaElementSource(audio);
    _vizAnalyser = _vizCtx.createAnalyser();
    _vizAnalyser.fftSize = 128;
    source.connect(_vizAnalyser);
    _vizAnalyser.connect(_vizCtx.destination);
    _drawVisualizer(canvas);
  } catch (e) {
    // Web Audio not supported or already connected
  }
}

function _drawVisualizer(canvas) {
  if (!_vizAnalyser) return;
  var ctx = canvas.getContext('2d');
  var bufferLength = _vizAnalyser.frequencyBinCount;
  var dataArray = new Uint8Array(bufferLength);

  function draw() {
    requestAnimationFrame(draw);
    _vizAnalyser.getByteFrequencyData(dataArray);

    var w = canvas.width = canvas.offsetWidth * (window.devicePixelRatio || 1);
    var h = canvas.height = canvas.offsetHeight * (window.devicePixelRatio || 1);
    ctx.clearRect(0, 0, w, h);

    var barCount = Math.min(bufferLength, 48);
    var barWidth = w / barCount;
    var gap = 2;

    for (var i = 0; i < barCount; i++) {
      var val = dataArray[i] / 255;
      var barHeight = val * h * 0.85;

      var gradient = ctx.createLinearGradient(0, h, 0, h - barHeight);
      gradient.addColorStop(0, 'rgba(124, 92, 252, 0.6)');
      gradient.addColorStop(1, 'rgba(139, 92, 246, 0.15)');
      ctx.fillStyle = gradient;

      var x = i * barWidth + gap / 2;
      ctx.beginPath();
      ctx.roundRect(x, h - barHeight, barWidth - gap, barHeight, 2);
      ctx.fill();
    }
  }
  draw();
}

// ───── Library Management (no reload) ─────

async function deleteTrack(id, title) {
  if (!confirm('Delete "' + title + '" permanently?')) return;
  var res = await api('/api/music/' + id, 'DELETE');
  if (res.error) { showToast(res.error, 'error'); return; }
  showToast('Track deleted', 'success');
  var row = document.querySelector('.track-row[data-id="' + id + '"]');
  if (row) {
    row.style.opacity = '0';
    row.style.transform = 'translateX(20px)';
    setTimeout(function() { row.remove(); }, 200);
  }
}

async function archiveTrack(id) {
  var res = await api('/api/music/' + id + '/archive', 'POST');
  if (res.error) { showToast(res.error, 'error'); return; }
  showToast('Track archived', 'info');
  var row = document.querySelector('.track-row[data-id="' + id + '"]');
  if (row) {
    row.style.opacity = '0';
    row.style.transform = 'translateX(20px)';
    setTimeout(function() { row.remove(); }, 200);
  }
}

async function unarchiveTrack(id) {
  var res = await api('/api/music/' + id + '/unarchive', 'POST');
  if (res.error) { showToast(res.error, 'error'); return; }
  showToast('Track restored', 'success');
  await _refreshTrackList();
}

// ───── Preset grid click handler ─────
var presetGrid = document.getElementById('preset-grid');
if (presetGrid) {
  presetGrid.addEventListener('click', function(e) {
    var btn = e.target.closest('.preset-btn');
    if (!btn) return;
    generateFromPreset(btn.dataset.name, btn.dataset.prompt);
  });
}
