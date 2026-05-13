/* plan page logic */

var _plan = { mood: null, track: null };
var _calYear = new Date().getFullYear();
var _calMonth = new Date().getMonth() + 1;
var _calSessions = [];
var _trackingLevel = document.body.dataset.trackingLevel || 'basic';

// ───── Persona ─────
async function setPersona(btn) {
  var key = btn.dataset.persona;
  document.querySelectorAll('.persona-pill').forEach(function(p) { p.classList.remove('active'); });
  btn.classList.add('active');
  try {
    await api('/api/user/preferences', 'POST', { persona: key || null });
    showToast(key ? 'Persona: ' + btn.textContent.trim() : 'Persona cleared', 'success');
  } catch (e) {
    showToast('Error saving persona', 'error');
  }
}

// ───── Calendar / Journal ─────
var _monthNames = ['January','February','March','April','May','June','July','August','September','October','November','December'];

function navCalendar(delta) {
  _calMonth += delta;
  if (_calMonth > 12) { _calMonth = 1; _calYear++; }
  if (_calMonth < 1) { _calMonth = 12; _calYear--; }
  loadCalendar(_calYear, _calMonth);
}

async function loadCalendar(year, month) {
  var label = document.getElementById('cal-month-label');
  if (label) label.textContent = _monthNames[month - 1] + ' ' + year;

  try {
    var data = await api('/api/sleep/calendar?year=' + year + '&month=' + month);
    _calSessions = data.sessions || [];
  } catch (e) {
    _calSessions = [];
  }
  renderCalendar(year, month, _calSessions);
}

function renderCalendar(year, month, sessions) {
  var grid = document.getElementById('cal-grid');
  if (!grid) return;

  while (grid.children.length > 7) grid.removeChild(grid.lastChild);

  var firstDay = new Date(year, month - 1, 1).getDay();
  var offset = (firstDay === 0) ? 6 : firstDay - 1;
  var daysInMonth = new Date(year, month, 0).getDate();

  var sessionMap = {};
  sessions.forEach(function(s) {
    var d = s.day;
    if (!sessionMap[d]) sessionMap[d] = [];
    sessionMap[d].push(s);
  });

  for (var i = 0; i < offset; i++) {
    var empty = document.createElement('div');
    empty.className = 'cal-day';
    grid.appendChild(empty);
  }

  for (var day = 1; day <= daysInMonth; day++) {
    var cell = document.createElement('div');
    cell.className = 'cal-day';
    cell.textContent = day;

    if (sessionMap[day]) {
      cell.classList.add('has-session');
      var best = sessionMap[day][0];
      var dot = document.createElement('span');
      dot.className = 'cal-dot';
      var rating = best.rating;
      if (rating === null || rating === undefined) {
        dot.classList.add('skip');
      } else if (rating >= 4) {
        dot.classList.add('good');
      } else if (rating >= 3) {
        dot.classList.add('mid');
      } else {
        dot.classList.add('bad');
      }
      cell.appendChild(dot);
      (function(d, ss) {
        cell.onclick = function() { showDayDetail(d, ss); };
      })(day, sessionMap[day]);
    }
    grid.appendChild(cell);
  }
}

function showDayDetail(day, sessions) {
  var detail = document.getElementById('cal-detail');
  if (!detail) return;
  detail.textContent = '';

  var heading = document.createElement('div');
  heading.style.fontWeight = '600';
  heading.style.marginBottom = '0.4rem';
  heading.textContent = _monthNames[_calMonth - 1] + ' ' + day;
  detail.appendChild(heading);

  sessions.forEach(function(s) {
    var entry = document.createElement('div');
    entry.style.marginBottom = '0.4rem';

    var score = document.createElement('span');
    score.style.color = 'var(--accent)';
    score.style.fontWeight = '600';
    score.textContent = s.rating ? s.rating + '/5' : 'skipped';
    entry.appendChild(score);

    if (s.duration) {
      var dur = document.createTextNode(' — ' + (s.duration / 60).toFixed(1) + 'h');
      entry.appendChild(dur);
    }
    if (s.track) {
      var sep = document.createTextNode(' — ');
      entry.appendChild(sep);
      var trackName = document.createElement('span');
      trackName.textContent = s.track;
      entry.appendChild(trackName);
    }
    detail.appendChild(entry);

    if (_trackingLevel === 'detailed' && s.session_id) {
      var factors = s.factors || [];
      var factorRow = document.createElement('div');
      factorRow.className = 'factor-row';
      factorRow.style.display = 'flex';
      factorRow.style.gap = '0.35rem';
      factorRow.style.flexWrap = 'wrap';
      factorRow.style.marginTop = '0.5rem';
      ['caffeine','exercise','screen_time','stress','alcohol','nap','late_meal'].forEach(function(f) {
        var chip = document.createElement('button');
        chip.className = 'factor-chip' + (factors.indexOf(f) >= 0 ? ' active' : '');
        chip.textContent = f.replace('_', ' ');
        chip.onclick = function() { toggleFactor(s.session_id, f, chip); };
        factorRow.appendChild(chip);
      });
      detail.appendChild(factorRow);
    }

    if (s.notes) {
      var note = document.createElement('div');
      note.style.color = 'var(--text-muted)';
      note.style.marginTop = '0.3rem';
      note.style.fontStyle = 'italic';
      note.textContent = s.notes;
      detail.appendChild(note);
    }
  });

  detail.classList.add('visible');
}

async function toggleFactor(sessionId, factor, btn) {
  btn.classList.toggle('active');
  var row = btn.parentElement;
  var factors = [];
  row.querySelectorAll('.factor-chip.active').forEach(function(c) {
    factors.push(c.textContent.trim().replace(/ /g, '_'));
  });
  try {
    await api('/api/sleep/factors', 'POST', { session_id: sessionId, factors: factors });
  } catch (e) {
    showToast('Error saving factors', 'error');
  }
}

async function setTrackingLevel(btn) {
  var level = btn.dataset.level;
  _trackingLevel = level;
  document.querySelectorAll('.tracking-opt').forEach(function(o) { o.classList.remove('active'); });
  btn.classList.add('active');
  try {
    await api('/api/user/preferences', 'POST', { tracking_level: level });
  } catch (e) {
    showToast('Error saving preference', 'error');
  }
}

// ───── Mood + Track selection ─────
function pickMood(btn) {
  document.querySelectorAll('.mood-btn').forEach(function(b) { b.classList.remove('active'); });
  btn.classList.add('active');
  _plan.mood = btn.dataset.mood;
  _sortTracksByMood(_plan.mood);
}

function _sortTracksByMood(mood) {
  var strip = document.getElementById('track-strip');
  if (!strip) return;
  var chips = Array.from(strip.querySelectorAll('.track-chip'));
  if (chips.length === 0) return;

  chips.sort(function(a, b) {
    var aTags = (a.dataset.moodTags || '').split(',');
    var bTags = (b.dataset.moodTags || '').split(',');
    var aMatch = aTags.indexOf(mood) >= 0 ? 1 : 0;
    var bMatch = bTags.indexOf(mood) >= 0 ? 1 : 0;
    return bMatch - aMatch;
  });

  chips.forEach(function(chip) {
    strip.appendChild(chip);
    var tags = (chip.dataset.moodTags || '').split(',');
    if (tags.indexOf(mood) >= 0) {
      chip.style.borderColor = 'rgba(124,92,252,0.3)';
    } else {
      chip.style.borderColor = '';
    }
  });
}

function pickTrack(chip) {
  document.querySelectorAll('.track-chip').forEach(function(c) { c.classList.remove('active'); });
  chip.classList.add('active');
  _plan.track = { id: chip.dataset.id, src: chip.dataset.src, title: chip.dataset.title };

  var preview = document.getElementById('track-preview');
  var title = document.getElementById('preview-title');
  preview.classList.add('visible');
  title.textContent = _plan.track.title;

  var audio = document.getElementById('preview-audio');
  audio.src = _plan.track.src;
  audio.volume = parseInt(document.getElementById('preview-vol').value) / 100;
}

function togglePreview() {
  var audio = document.getElementById('preview-audio');
  if (!audio.src) return;
  if (audio.paused) {
    audio.play().catch(function(){});
  } else {
    audio.pause();
  }
}

function setPreviewVol(val) {
  var audio = document.getElementById('preview-audio');
  if (audio) audio.volume = parseInt(val) / 100;
}

// Preview play/pause icon swap
(function() {
  var audio = document.getElementById('preview-audio');
  if (!audio) return;
  var icon = document.getElementById('preview-icon');
  audio.addEventListener('play', function() {
    icon.replaceChildren();
    var r1 = document.createElementNS('http://www.w3.org/2000/svg','rect');
    r1.setAttribute('x','6'); r1.setAttribute('y','4'); r1.setAttribute('width','4'); r1.setAttribute('height','16');
    var r2 = document.createElementNS('http://www.w3.org/2000/svg','rect');
    r2.setAttribute('x','14'); r2.setAttribute('y','4'); r2.setAttribute('width','4'); r2.setAttribute('height','16');
    icon.appendChild(r1); icon.appendChild(r2);
  });
  audio.addEventListener('pause', function() {
    icon.replaceChildren();
    var poly = document.createElementNS('http://www.w3.org/2000/svg','polygon');
    poly.setAttribute('points','5 3 19 12 5 21 5 3');
    icon.appendChild(poly);
  });
})();


// Select the MongoDB-recommended mood once the plan card is present.
(function() {
  var card = document.getElementById('plan-card');
  if (!card) return;
  var mood = card.dataset.recommendedMood || 'calm';
  var btn = document.querySelector('.mood-btn[data-mood="' + mood + '"]') || document.querySelector('.mood-btn[data-mood="calm"]');
  if (btn) pickMood(btn);
})();

// ───── Start sleep ─────
function _resolveTrack() {
  if (_plan.track) return _plan.track;
  var chips = document.querySelectorAll('.track-chip');
  if (chips.length > 0) {
    var c = chips[0];
    return { id: c.dataset.id, src: c.dataset.src, title: c.dataset.title };
  }
  return null;
}

async function startSleep() {
  var btn = document.getElementById('btn-start');
  btn.disabled = true;
  btn.textContent = 'Setting up...';

  var preview = document.getElementById('preview-audio');
  if (preview) preview.pause();

  var track = _resolveTrack();
  var plan = {
    mood: _plan.mood || 'calm',
    soundscape_title: track ? track.title : null,
    soundscape_id: track ? track.id : null,
    soundscape_src: track ? track.src : null,
    duration_hours: 7.5,
    wind_down: '4-7-8 breathing',
  };

  try {
    var data = await api('/api/sleep/plan', 'POST', plan);
    if (data.session_id) {
      var params = new URLSearchParams();
      params.set('session', data.session_id);
      if (data.playlist && data.playlist.playlist_id) {
        params.set('playlist', data.playlist.playlist_id);
      }
      if (plan.soundscape_src) params.set('track', plan.soundscape_src);
      if (plan.soundscape_title) params.set('title', plan.soundscape_title);
      window.location.href = '/sleep?' + params.toString();
    } else {
      showToast(data.error || 'Failed to create session', 'error');
      btn.disabled = false;
      btn.textContent = 'Start Sleep';
    }
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
    btn.disabled = false;
    btn.textContent = 'Start Sleep';
  }
}

// ───── Sound Lab ─────
async function generateTrack() {
  var prompt = document.getElementById('lab-prompt').value.trim();
  if (!prompt) { showToast('Describe a soundscape first', 'error'); return; }
  generateMusic(prompt, prompt.substring(0, 50));
}

// ───── Review ─────
async function submitReview(sid, rating) {
  await api('/api/sleep/review', 'POST', { session_id: sid, rating: rating });
  var banner = document.querySelector('section');
  if (banner) { banner.style.opacity = '0'; setTimeout(function() { banner.remove(); }, 300); }
  showToast('Thanks!', 'success');
}

async function skipReview(sid) {
  await api('/api/sleep/review', 'POST', { session_id: sid, skip: true });
  var banner = document.querySelector('section');
  if (banner) { banner.style.opacity = '0'; setTimeout(function() { banner.remove(); }, 300); }
}

// ───── Packs ─────
(function() {
  var section = document.getElementById('packs-section');
  if (!section) return;
  var loaded = false;
  section.addEventListener('toggle', async function() {
    if (!section.open || loaded) return;
    loaded = true;
    var list = document.getElementById('packs-list');
    try {
      var packs = await api('/api/packs');
      list.textContent = '';
      if (!packs || packs.length === 0) {
        var empty = document.createElement('div');
        empty.className = 'text-xs text-white/30 py-2';
        empty.textContent = 'No packs available yet.';
        list.appendChild(empty);
        return;
      }
      packs.forEach(function(p) {
        var row = document.createElement('div');
        row.className = 'flex items-center gap-3 py-2 border-b border-border';
        var info = document.createElement('div');
        info.className = 'flex-1';
        var name = document.createElement('div');
        name.className = 'text-sm font-medium text-white';
        name.textContent = p.name;
        var desc = document.createElement('div');
        desc.className = 'text-[0.65rem] text-white/30';
        desc.textContent = (p.description || '') + ' · ' + (p.track_ids ? p.track_ids.length : 0) + ' tracks';
        info.appendChild(name);
        info.appendChild(desc);
        var btn = document.createElement('button');
        btn.className = 'btn btn-sm btn-ghost';
        btn.textContent = p.price_credits + ' credits';
        btn.onclick = function() { purchasePack(p.slug); };
        row.appendChild(info);
        row.appendChild(btn);
        list.appendChild(row);
      });
    } catch (e) {
      list.textContent = '';
      var err = document.createElement('div');
      err.className = 'text-xs text-white/30 py-2';
      err.textContent = 'Error loading packs.';
      list.appendChild(err);
    }
  });
})();

async function purchasePack(slug) {
  try {
    var result = await api('/api/packs/' + slug + '/purchase', 'POST');
    if (result.error) {
      showToast(result.error, 'error');
    } else {
      showToast('Purchased ' + result.pack + '!', 'success');
    }
  } catch (e) {
    showToast('Error: ' + (e.message || 'Purchase failed'), 'error');
  }
}

// ───── Library seeding poll ─────
(function() {
  var seedEl = document.getElementById('track-seeding');
  if (!seedEl) return;
  var _pollCount = 0;
  var _pollInterval = setInterval(async function() {
    _pollCount++;
    if (_pollCount > 20) { clearInterval(_pollInterval); seedEl.remove(); return; }
    try {
      var tracks = await api('/api/music/library');
      if (Array.isArray(tracks) && tracks.length >= 5) {
        clearInterval(_pollInterval);
        seedEl.remove();
        _refreshTrackList();
      } else if (Array.isArray(tracks)) {
        var strip = document.getElementById('track-strip');
        if (strip) {
          var existing = strip.querySelectorAll('.track-chip').length;
          if (tracks.length > existing) _refreshTrackList();
        }
      }
    } catch (e) {}
  }, 30000);
})();

// ───── Agent auto-greet ─────
(function() {
  var messages = document.getElementById('chat-messages');
  if (!messages) return;

  function addMsg(text, cls) {
    var div = document.createElement('div');
    div.className = 'msg ' + cls;
    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    return div;
  }

  setTimeout(async function() {
    var thinking = addMsg('Checking your sleep history...', 'msg-agent msg-thinking');
    try {
      var data = await api('/api/chat', 'POST', { message: 'I just opened the app. Check my sleep history and recommend what I should listen to tonight.' });
      thinking.classList.remove('msg-thinking');
      var resp = data.response || 'Ready when you are.';
      thinking.textContent = resp;
      if (resp.includes('/sleep?')) {
        var match = resp.match(/(\/sleep\?[^\s"']+)/);
        if (match) {
          var link = document.createElement('div');
          link.className = 'msg msg-agent';
          var a = document.createElement('a');
          a.href = match[1];
          a.style.color = 'var(--accent)';
          a.textContent = 'Start session →';
          link.appendChild(a);
          messages.appendChild(link);
          messages.scrollTop = messages.scrollHeight;
        }
      }
    } catch (e) {
      thinking.classList.remove('msg-thinking');
      thinking.textContent = 'Ready when you are.';
    }
  }, 2500);
})();

// Init calendar on load
(function() {
  var grid = document.getElementById('cal-grid');
  if (grid) loadCalendar(_calYear, _calMonth);
})();
