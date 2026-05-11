async function api(url, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  return res.json();
}

function startBedtime(name, soundType, maxVolume, fadeMinutes) {
  api('/api/play', 'POST', {
    sound_type: soundType,
    duration_minutes: 30,
    volume: maxVolume,
  }).then(() => {
    refreshStatus();
    setTimeout(() => {
      api('/api/fade', 'POST', {
        target: 0,
        seconds: fadeMinutes * 60,
      });
    }, (30 - fadeMinutes) * 60 * 1000);
  });
}

function stopPlayback() {
  api('/api/stop', 'POST').then(() => refreshStatus());
}

function setVolume(val) {
  document.getElementById('vol-display').textContent = val;
  api('/api/volume', 'POST', { volume: parseInt(val) });
}

function fadeOut() {
  api('/api/fade', 'POST', { target: 0, seconds: 900 });
}

async function refreshStatus() {
  const s = await api('/api/status');
  const display = document.getElementById('status-display');
  if (!display) return;
  if (s.is_playing) {
    display.innerHTML = `
      <div class="status-active">
        <span class="pulse"></span>
        <span>${s.sound_name || 'Playing'}</span>
      </div>`;
  } else {
    display.innerHTML = '<div class="status-idle">Nothing playing</div>';
  }
  const slider = document.getElementById('volume-slider');
  if (slider) slider.value = s.volume;
  const volDisplay = document.getElementById('vol-display');
  if (volDisplay) volDisplay.textContent = s.volume;
}

async function sendChat(e) {
  e.preventDefault();
  const input = document.getElementById('chat-input');
  const msg = input.value.trim();
  if (!msg) return;

  const messages = document.getElementById('chat-messages');
  messages.innerHTML += `<div class="msg msg-user">${escapeHtml(msg)}</div>`;
  input.value = '';
  messages.scrollTop = messages.scrollHeight;

  const thinking = document.createElement('div');
  thinking.className = 'msg msg-agent';
  thinking.textContent = 'Thinking...';
  messages.appendChild(thinking);
  messages.scrollTop = messages.scrollHeight;

  const data = await api('/api/chat', 'POST', { message: msg });
  thinking.textContent = data.response || data.error || 'No response';
  messages.scrollTop = messages.scrollHeight;
}

async function createProfile(e) {
  e.preventDefault();
  await api('/api/profiles', 'POST', {
    name: document.getElementById('p-name').value,
    bedtime: document.getElementById('p-bedtime').value,
    max_volume: parseInt(document.getElementById('p-volume').value),
    fade_minutes: parseInt(document.getElementById('p-fade').value),
  });
  location.reload();
}

async function deleteProfile(name) {
  if (!confirm(`Remove profile "${name}"?`)) return;
  await api(`/api/profiles/${encodeURIComponent(name)}`, 'DELETE');
  location.reload();
}

async function createSchedule(e) {
  e.preventDefault();
  await api('/api/schedules', 'POST', {
    profile_name: document.getElementById('s-profile').value,
    sound_type: document.getElementById('s-sound').value,
    start_time: document.getElementById('s-time').value,
    duration_minutes: parseInt(document.getElementById('s-duration').value),
    fade_out_minutes: parseInt(document.getElementById('s-fade').value),
    volume: parseInt(document.getElementById('s-volume').value),
    recurring: document.getElementById('s-recurring').checked,
  });
  location.reload();
}

async function deleteSchedule(id) {
  await api(`/api/schedules/${id}`, 'DELETE');
  location.reload();
}

// ───── Music Generation ─────

function _scrollToLibrary() {
  var url = new URL(window.location.href);
  url.searchParams.set('t', Date.now());
  url.hash = 'track-list';
  window.location.href = url.toString();
}

async function generateMusic(prompt, title) {
  const overlay = document.getElementById('gen-loading');
  if (overlay) overlay.classList.add('active');
  try {
    const res = await api('/api/music/generate', 'POST', { prompt, title });
    if (res.error) {
      alert(res.error);
    } else {
      _scrollToLibrary();
    }
  } catch (e) {
    alert('Generation failed: ' + e.message);
  } finally {
    if (overlay) overlay.classList.remove('active');
  }
}

function generateFromPreset(name, prompt) {
  generateMusic(prompt, name);
}

async function generateCustom(e) {
  e.preventDefault();
  const input = document.getElementById('custom-prompt');
  const prompt = input.value.trim();
  if (!prompt) return;
  generateMusic(prompt, '');
}

async function generateNasa() {
  const overlay = document.getElementById('gen-loading');
  if (overlay) overlay.classList.add('active');
  try {
    const res = await api('/api/music/nasa', 'POST', {});
    if (res.error) {
      alert(res.error);
    } else {
      _scrollToLibrary();
    }
  } catch (e) {
    alert('NASA generation failed: ' + e.message);
  } finally {
    if (overlay) overlay.classList.remove('active');
  }
}

// ───── Inspire & Variations ─────

async function inspireMe() {
  var btn = document.getElementById('inspire-btn');
  var grid = document.getElementById('suggest-grid');
  if (!btn || !grid) return;

  btn.disabled = true;
  btn.classList.add('loading');
  grid.replaceChildren();

  try {
    var suggestions = await api('/api/music/suggest');
    if (!Array.isArray(suggestions) || suggestions.length === 0) {
      btn.disabled = false;
      btn.classList.remove('loading');
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
    // silent fail
  }
  btn.disabled = false;
  btn.classList.remove('loading');
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

const queue = [];
let queueIndex = -1;

function _audio() { return document.getElementById('player-audio'); }

function _formatTime(s) {
  if (!s || isNaN(s)) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return m + ':' + (sec < 10 ? '0' : '') + sec;
}

function _updatePlayerUI() {
  const audio = _audio();
  if (!audio) return;
  const player = document.getElementById('player');
  const titleEl = document.getElementById('player-title');
  const icon = document.getElementById('player-play-icon');
  const current = queueIndex >= 0 && queueIndex < queue.length ? queue[queueIndex] : null;

  if (current) {
    titleEl.textContent = current.title;
    player.classList.add('has-track');
  } else {
    titleEl.textContent = 'No track selected';
    player.classList.remove('has-track');
  }

  // swap play/pause icon using DOM
  icon.replaceChildren();
  if (audio.paused) {
    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('points', '5 3 19 12 5 21 5 3');
    icon.appendChild(poly);
  } else {
    const r1 = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    r1.setAttribute('x','6'); r1.setAttribute('y','4'); r1.setAttribute('width','4'); r1.setAttribute('height','16');
    const r2 = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    r2.setAttribute('x','14'); r2.setAttribute('y','4'); r2.setAttribute('width','4'); r2.setAttribute('height','16');
    icon.appendChild(r1);
    icon.appendChild(r2);
  }

  // highlight active row
  document.querySelectorAll('.track-row').forEach(function(r) { r.classList.remove('active'); });
  if (current) {
    const row = document.querySelector('.track-row[data-src="' + current.src + '"]');
    if (row) row.classList.add('active');
  }

  _renderQueue();
}

function _renderQueue() {
  const section = document.getElementById('queue-section');
  const list = document.getElementById('queue-list');
  if (!section || !list) return;

  const upcoming = queue.slice(queueIndex + 1);
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
  audio.play();
  _updatePlayerUI();
}

function playerToggle() {
  var audio = _audio();
  if (!audio) return;
  if (audio.src && !audio.paused) {
    audio.pause();
  } else if (audio.src) {
    audio.play();
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
  if (queue.some(function(t) { return t.src === src; })) return;
  queue.push({ src: src, title: title, path: path });
  if (queue.length === 1) {
    queueIndex = 0;
    _loadAndPlay();
  }
  _renderQueue();
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

function playOnSpeaker(path) {
  api('/api/music/play', 'POST', { path });
}

// Player time/progress updates
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

// ───── Library Management ─────

async function deleteTrack(id, title) {
  if (!confirm('Delete "' + title + '" permanently? This cannot be undone.')) return;
  await api('/api/music/' + id, 'DELETE');
  location.reload();
}

async function archiveTrack(id) {
  await api('/api/music/' + id + '/archive', 'POST');
  location.reload();
}

async function unarchiveTrack(id) {
  await api('/api/music/' + id + '/unarchive', 'POST');
  location.reload();
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

if (document.getElementById('status-display')) {
  setInterval(refreshStatus, 5000);
}

const presetGrid = document.getElementById('preset-grid');
if (presetGrid) {
  presetGrid.addEventListener('click', function(e) {
    const btn = e.target.closest('.preset-btn');
    if (!btn) return;
    generateFromPreset(btn.dataset.name, btn.dataset.prompt);
  });
}
