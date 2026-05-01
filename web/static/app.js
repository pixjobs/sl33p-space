async function api(url, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  return res.json();
}

function quickPlay(soundType) {
  api('/api/play', 'POST', { sound_type: soundType, duration_minutes: 30 })
    .then(() => refreshStatus());
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

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

if (document.getElementById('status-display')) {
  setInterval(refreshStatus, 5000);
}
