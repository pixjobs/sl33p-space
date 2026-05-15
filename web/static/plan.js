/* plan page logic */

// ───── Tabs ─────
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(function(t) { t.classList.toggle('active', t.dataset.tab === name); });
  document.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.toggle('active', p.id === 'panel-' + name); });
  if (name === 'insights') loadRecentSessions();
}

var _plan = { mood: null, track: null };
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

// ───── Recent Sessions ─────

async function loadRecentSessions() {
  var list = document.getElementById('recent-sessions');
  if (!list) return;
  try {
    var data = await api('/api/sleep/history');
    var sessions = data.sessions || [];
    list.textContent = '';
    if (sessions.length === 0) {
      var empty = document.createElement('li');
      empty.className = 'recent-empty';
      empty.textContent = 'No sessions yet. Start one tonight!';
      list.appendChild(empty);
      return;
    }
    sessions.forEach(function(s) {
      var li = document.createElement('li');
      li.className = 'recent-row';

      var plan = s.plan || {};
      var review = s.review || {};
      var actual = s.actual || {};
      var rating = review.rating;
      var factors = s.factors || [];
      var sid = s._id;
      var date = s.created_at ? new Date(s.created_at) : null;

      // Top row: date + track + rating + delete
      var top = document.createElement('div');
      top.className = 'recent-row-top';

      var dateEl = document.createElement('span');
      dateEl.className = 'recent-date';
      dateEl.textContent = date ? date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '?';
      top.appendChild(dateEl);

      var title = document.createElement('span');
      title.className = 'recent-title';
      title.textContent = plan.soundscape_title || 'Untitled';
      top.appendChild(title);

      if (actual.duration_minutes) {
        var dur = document.createElement('span');
        dur.className = 'recent-dur';
        dur.textContent = actual.duration_minutes >= 60
          ? (actual.duration_minutes / 60).toFixed(1) + 'h'
          : Math.round(actual.duration_minutes) + 'm';
        top.appendChild(dur);
      }

      var badge = document.createElement('span');
      badge.className = 'journal-rating-badge';
      if (rating) {
        if (rating >= 4) badge.classList.add('good');
        else if (rating >= 3) badge.classList.add('mid');
        else badge.classList.add('bad');
        badge.textContent = rating + '/5';
      } else {
        badge.classList.add('skip');
        badge.textContent = '-';
      }
      top.appendChild(badge);

      // Delete button
      if (sid) {
        var delBtn = document.createElement('button');
        delBtn.className = 'journal-delete-btn';
        delBtn.innerHTML = '&times;';
        delBtn.title = 'Delete session';
        (function(id, rowEl, btn) {
          var armed = false;
          btn.onclick = function(e) {
            e.stopPropagation();
            if (!armed) {
              armed = true;
              btn.textContent = 'Delete?';
              btn.classList.add('armed');
              setTimeout(function() { if (armed) { armed = false; btn.innerHTML = '&times;'; btn.classList.remove('armed'); } }, 3000);
            } else {
              api('/api/sleep/delete', 'POST', { session_id: id }).then(function() {
                rowEl.style.opacity = '0';
                setTimeout(function() { rowEl.remove(); }, 200);
                showToast('Session deleted', 'success');
              });
            }
          };
        })(sid, li, delBtn);
        top.appendChild(delBtn);
      }

      li.appendChild(top);

      // Factor tags (read-only display, tap row to edit)
      if (factors.length > 0) {
        var tagRow = document.createElement('div');
        tagRow.className = 'recent-tags';
        factors.forEach(function(f) {
          var tag = document.createElement('span');
          tag.className = 'recent-tag';
          tag.textContent = f.replace(/_/g, ' ');
          tagRow.appendChild(tag);
        });
        li.appendChild(tagRow);
      }

      // Expandable factor editor (hidden by default)
      var detail = document.createElement('div');
      detail.className = 'recent-detail hidden';
      if (sid) {
        var factorRow = document.createElement('div');
        factorRow.className = 'journal-factors';
        ['caffeine','exercise','screen_time','stress','alcohol','nap','late_meal'].forEach(function(f) {
          var chip = document.createElement('button');
          chip.className = 'factor-chip' + (factors.indexOf(f) >= 0 ? ' active' : '');
          chip.textContent = f.replace(/_/g, ' ');
          chip.onclick = function(e) { e.stopPropagation(); toggleFactor(sid, f, chip); };
          factorRow.appendChild(chip);
        });
        detail.appendChild(factorRow);
      }
      li.appendChild(detail);

      // Toggle detail on row tap
      top.style.cursor = 'pointer';
      (function(det) {
        top.onclick = function() { det.classList.toggle('hidden'); };
      })(detail);

      list.appendChild(li);
    });
  } catch (e) {
    list.textContent = '';
    var err = document.createElement('li');
    err.className = 'recent-empty';
    err.textContent = 'Could not load sessions';
    list.appendChild(err);
  }
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
      if (_plan.mood) params.set('mood', _plan.mood);
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

// ───── Manual Sleep Log ─────
function toggleManualLog() {
  var form = document.getElementById('manual-log-form');
  if (form) form.classList.toggle('hidden');
}

async function submitManualLog() {
  var bed = document.getElementById('manual-bed').value;
  var wake = document.getElementById('manual-wake').value;
  if (!bed || !wake) { showToast('Set both times', 'error'); return; }
  var btn = document.getElementById('btn-manual-log');
  if (btn) { btn.disabled = true; btn.textContent = 'Logging...'; }
  try {
    await api('/api/sleep/log', 'POST', { bed_time: bed, wake_time: wake, mood: _plan.mood || 'calm' });
    showToast('Sleep logged!', 'success');
    setTimeout(function() { location.reload(); }, 600);
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
    if (btn) { btn.disabled = false; btn.textContent = 'Log it'; }
  }
}

// ───── Sound Lab ─────
async function generateTrack() {
  var prompt = document.getElementById('lab-prompt').value.trim();
  if (!prompt) { showToast('Describe a soundscape first', 'error'); return; }
  generateMusic(prompt, prompt.substring(0, 50));
}

// ───── Review ─────
var _reviewRating = null;
var _reviewMetrics = {};

function selectReviewRating(btn, rating) {
  _reviewRating = rating;
  document.querySelectorAll('#review-stars .review-star-btn').forEach(function(b) {
    b.classList.toggle('active', parseInt(b.dataset.rating) === rating);
  });
  var submit = document.getElementById('review-submit-btn');
  if (submit) submit.disabled = false;
  var detail = document.getElementById('review-detail');
  if (detail) detail.classList.remove('hidden');
}

function selectMetric(key, btn, val) {
  _reviewMetrics[key] = val;
  var group = btn.parentElement;
  group.querySelectorAll('.metric-btn').forEach(function(b) {
    b.classList.toggle('active', parseInt(b.dataset.val) === val);
  });
}

function toggleReviewFactor(btn) {
  btn.classList.toggle('active');
}

async function submitBannerReview(sid) {
  var factors = [];
  document.querySelectorAll('#review-factors .factor-chip-review.active').forEach(function(c) {
    factors.push(c.dataset.factor);
  });
  var notes = (document.getElementById('review-notes') || {}).value || '';
  var metrics = Object.keys(_reviewMetrics).length > 0 ? _reviewMetrics : null;
  var btn = document.getElementById('review-submit-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Saving...'; }
  try {
    await api('/api/sleep/review', 'POST', { session_id: sid, rating: _reviewRating, factors: factors, metrics: metrics, notes: notes });
    var banner = document.getElementById('review-banner');
    if (banner) { banner.style.opacity = '0'; setTimeout(function() { banner.remove(); }, 300); }
    showToast('Review saved', 'success');
  } catch (e) {
    if (btn) { btn.disabled = false; btn.textContent = 'Save'; }
    showToast('Error: ' + e.message, 'error');
  }
}

async function submitReview(sid, rating) {
  await api('/api/sleep/review', 'POST', { session_id: sid, rating: rating });
  var banner = document.getElementById('review-banner');
  if (banner) { banner.style.opacity = '0'; setTimeout(function() { banner.remove(); }, 300); }
  showToast('Thanks!', 'success');
}

async function skipReview(sid) {
  await api('/api/sleep/review', 'POST', { session_id: sid, skip: true });
  var banner = document.getElementById('review-banner');
  if (banner) { banner.style.opacity = '0'; setTimeout(function() { banner.remove(); }, 300); }
}

// ───── Referral ─────
var _referralLoaded = false;
function toggleReferralPanel() {
  var panel = document.getElementById('referral-panel');
  if (!panel) return;
  var hidden = panel.classList.toggle('hidden');
  if (!hidden && !_referralLoaded) {
    _referralLoaded = true;
    api('/api/user/referral').then(function(data) {
      var input = document.getElementById('referral-link');
      if (input && data.code) {
        input.value = window.location.origin + '/refer/' + data.code;
      }
      var stats = document.getElementById('referral-stats');
      if (stats && data.referrals_given !== undefined) {
        stats.textContent = data.referrals_given + ' referral' + (data.referrals_given !== 1 ? 's' : '') + ' given (max ' + (data.max_referrals || 5) + ')';
      }
    });
  }
}

function copyReferralLink() {
  var input = document.getElementById('referral-link');
  if (!input || !input.value) return;
  navigator.clipboard.writeText(input.value).then(function() {
    showToast('Referral link copied!', 'success');
  });
}

function shareReferralLink() {
  var input = document.getElementById('referral-link');
  var url = (input && input.value) ? input.value : window.location.origin;
  if (navigator.share) {
    navigator.share({ title: 'sl33p-space', text: 'Check out sl33p-space — AI sleep soundscapes', url: url });
  } else {
    navigator.clipboard.writeText(url).then(function() {
      showToast('Link copied!', 'success');
    });
  }
}

// ───── Gift banner ─────
async function dismissGiftBanner() {
  await api('/api/user/gifts/dismiss', 'POST');
  var banner = document.getElementById('gift-banner');
  if (banner) { banner.style.opacity = '0'; setTimeout(function() { banner.remove(); }, 300); }
}

// ───── Active session ─────
async function endActiveSession(sid) {
  await api('/api/sleep/end', 'POST', { session_id: sid });
  var banner = document.getElementById('active-session-banner');
  if (banner) { banner.style.opacity = '0'; setTimeout(function() { banner.remove(); }, 300); }
  showToast('Session ended', 'success');
  setTimeout(function() { location.reload(); }, 500);
}

// ───── Library scope filter ─────
function filterTracks(scope, btn) {
  document.querySelectorAll('.scope-pill').forEach(function(p) { p.classList.remove('active'); });
  if (btn) btn.classList.add('active');
  var chips = document.querySelectorAll('.track-chip');
  var visibleCount = 0;
  chips.forEach(function(chip) {
    var owner = chip.dataset.owner || 'public';
    if (scope === 'all' || owner === scope) {
      chip.style.display = '';
      visibleCount++;
    } else {
      chip.style.display = 'none';
    }
  });
  var strip = document.getElementById('track-strip');
  var empty = strip.querySelector('.scope-empty');
  if (visibleCount === 0 && !empty) {
    var span = document.createElement('span');
    span.className = 'col-span-2 text-xs text-white/30 py-2 scope-empty';
    span.textContent = scope === 'mine' ? 'No tracks yet — create one in the Create tab!' : 'No public tracks available';
    strip.appendChild(span);
  } else if (visibleCount > 0 && empty) {
    empty.remove();
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

// ───── Agent Card (Tonight tab, top) ─────
var _agentRec = null;
var _agentChatOpen = false;

function toggleAgentChat() {
  var panel = document.getElementById('agent-chat-panel');
  var btn = document.getElementById('agent-expand-btn');
  if (!panel) return;
  _agentChatOpen = !_agentChatOpen;
  panel.classList.toggle('hidden', !_agentChatOpen);
  if (btn) btn.classList.toggle('active', _agentChatOpen);
  if (_agentChatOpen && !_agentChatGreeted) {
    _agentChatGreeted = true;
    _autoGreetChat();
  }
}

var _agentChatGreeted = false;
function _autoGreetChat() {
  var messages = document.getElementById('chat-messages');
  if (!messages) return;
  var ref = _addChatRow(messages, 'Checking your sleep history...', 'agent', { raw: true, thinking: true });
  (async function() {
    try {
      var data = await api('/api/chat', 'POST', { message: 'I just opened the app. Check my sleep history and recommend what I should listen to tonight.' });
      var resp = data.response || 'Ready when you are.';
      ref.bubble.classList.remove('thinking');
      ref.bubble.innerHTML = _renderMd(resp);
      messages.scrollTop = messages.scrollHeight;
    } catch (e) {
      ref.bubble.classList.remove('thinking');
      ref.bubble.textContent = 'Ready when you are.';
    }
  })();
}

function dismissAgentRec() {
  var content = document.getElementById('agent-rec-content');
  if (content) content.classList.add('hidden');
  var empty = document.getElementById('agent-rec-empty');
  if (empty) empty.classList.remove('hidden');
}

// Load agent recommendation on page load
(function() {
  var recCard = document.getElementById('agent-card');
  if (!recCard) return;
  (async function() {
    try {
      var data = await api('/api/sleep/recommend', 'POST', { mood: _plan.mood || 'calm' });
      var loading = document.getElementById('agent-rec-loading');
      var content = document.getElementById('agent-rec-content');
      var empty = document.getElementById('agent-rec-empty');
      if (loading) loading.classList.add('hidden');
      if (data && data.reasoning) {
        _agentRec = data;
        var text = document.getElementById('agent-rec-text');
        if (text) text.textContent = data.reasoning + (data.soundscape_title ? ' — Try "' + data.soundscape_title + '"' : '');
        if (content) content.classList.remove('hidden');
      } else {
        if (empty) empty.classList.remove('hidden');
      }
    } catch (e) {
      var loading = document.getElementById('agent-rec-loading');
      var empty = document.getElementById('agent-rec-empty');
      if (loading) loading.classList.add('hidden');
      if (empty) empty.classList.remove('hidden');
    }
  })();
})();

function useAgentPlan() {
  if (!_agentRec) return;
  if (_agentRec.soundscape_title) {
    var chips = document.querySelectorAll('.track-chip');
    for (var i = 0; i < chips.length; i++) {
      if (chips[i].dataset.title === _agentRec.soundscape_title) {
        pickTrack(chips[i]);
        break;
      }
    }
  }
  var content = document.getElementById('agent-rec-content');
  if (content) content.classList.add('hidden');
  var planCard = document.getElementById('plan-card');
  if (planCard) planCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
  showToast('Plan applied', 'success');
}

// ───── APOD Background ─────
(function() {
  var bg = document.getElementById('plan-bg-apod');
  if (!bg) return;
  api('/api/scenes/cosmos').then(function(data) {
    if (data && data.images && data.images.length > 0) {
      var img = data.images[Math.floor(Math.random() * data.images.length)];
      var preload = new Image();
      preload.onload = function() {
        bg.style.backgroundImage = 'url(' + img.url + ')';
        bg.classList.add('loaded');
      };
      preload.src = img.url;
    }
  }).catch(function() {});
})();

// ───── Sound Lab Wizard ─────
var _lab = { step: 1, theme: null, keywords: [], colour: null, apodTitle: '', apodExplanation: '' };

var _labThemePrompts = {
  cosmic: 'Deep space ambient soundscape with vast nebula drones, cosmic reverb, and interstellar pad textures',
  rain: 'Soft rainfall ambience with distant rolling thunder, gentle wind, and cozy indoor warmth',
  forest: 'Nighttime forest atmosphere with soft crickets, distant owl calls, and gentle breeze through pine trees',
  ocean: 'Deep ocean underwater ambience with gentle currents, distant whale song, and bioluminescent shimmer',
  warmth: 'Warm analog vinyl ambience with tape saturation, soft crackle, and slow jazz-influenced chord progressions',
  zen: 'Tibetan singing bowls resonating in a mountain cave, deep meditative overtones, and tranquil stillness',
  dream: 'Ethereal floating ambient with crystalline arpeggios, vast reverb spaces, and weightless pad textures'
};

var _labKeywordDescriptions = {
  pads: 'warm evolving synthesizer pads',
  piano: 'sparse piano notes with long reverb tails',
  strings: 'slow legato string ensemble',
  bells: 'gentle bell tones and chime-like resonances',
  guitar: 'soft fingerpicked acoustic guitar',
  bowls: 'singing bowls with deep resonant overtones',
  clarinet: 'breathy clarinet with slow melodic phrases',
  saxophone: 'soft tenor saxophone with warm jazzy tones',
  cymbal: 'gentle cymbal swells and shimmering rides',
  granular: 'granular synthesis textures and micro-sound particles',
  tape_hiss: 'warm analog tape hiss and saturation',
  vinyl_crackle: 'vintage vinyl crackle and warmth',
  static: 'soft static and white noise textures',
  rain: 'gentle rainfall and water droplets',
  wind: 'soft wind and breeze sounds',
  waves: 'ocean waves lapping gently',
  crickets: 'nighttime crickets and insects',
  thunder: 'distant rolling thunder',
  whisper: 'soft ASMR whisper textures',
  tapping: 'gentle rhythmic tapping sounds',
  scratching: 'soft scratching and texture sounds',
  brushing: 'light brushing and sweeping sounds',
  crackling: 'warm fire crackling and popping',
  pages: 'slow page turning and paper rustling',
  minimal: 'minimal and spacious arrangement',
  layered: 'densely layered and rich',
  spacious: 'vast reverb and open spaces',
  warm: 'warm and cozy tonal character',
  cold: 'cool crystalline and icy textures'
};

var _labColourDescriptions = {
  indigo: 'deep and vast with cosmic reverb spaces',
  blue: 'cool and crystalline with calm floating tones',
  teal: 'fluid and oceanic with gentle flowing movement',
  green: 'organic and earthy with grounding natural textures',
  rose: 'soft and warm with dreamy rosy undertones',
  amber: 'warm analog vintage with golden tape-saturated tones',
  violet: 'ethereal and mystical with shimmering spectral textures',
  silver: 'pure and minimal with clean silver-toned clarity'
};

function labUpdateCharCount() {
  var txt = document.getElementById('lab-custom-text');
  var counter = document.getElementById('lab-char-count');
  if (txt && counter) counter.textContent = txt.value.length + '/500';
}

function labSelectTheme(el) {
  document.querySelectorAll('.lab-theme-card, .lab-apod-card').forEach(function(c) { c.classList.remove('active'); });
  el.classList.add('active');
  _lab.theme = el.dataset.theme;
  _lab.apodTitle = el.dataset.apodTitle || '';
  _lab.apodExplanation = el.dataset.apodExplanation || '';

  var customInput = document.getElementById('lab-custom-input');
  if (customInput) {
    customInput.classList.toggle('hidden', _lab.theme !== 'custom');
  }

  if (_lab.theme !== 'custom') {
    labNext();
  }
}

function labToggleKeyword(el) {
  var kw = el.dataset.keyword;
  var idx = _lab.keywords.indexOf(kw);
  if (idx >= 0) { _lab.keywords.splice(idx, 1); el.classList.remove('active'); }
  else { _lab.keywords.push(kw); el.classList.add('active'); }
}

function labSelectColour(el) {
  document.querySelectorAll('.lab-colour-swatch').forEach(function(s) { s.classList.remove('active'); });
  el.classList.add('active');
  _lab.colour = el.dataset.colour;
  _labBuildPreview();
  var preview = document.getElementById('lab-preview-prompt');
  if (preview) preview.classList.remove('hidden');
}

function _labUpdateDots() {
  document.querySelectorAll('.lab-dot').forEach(function(dot) {
    var s = parseInt(dot.dataset.step);
    dot.classList.remove('active', 'done');
    if (s === _lab.step) dot.classList.add('active');
    else if (s < _lab.step) dot.classList.add('done');
  });
}

function labNext() {
  if (_lab.step === 1 && !_lab.theme) { showToast('Pick a theme first', 'error'); return; }
  if (_lab.step === 1 && _lab.theme === 'custom') {
    var txt = (document.getElementById('lab-custom-text') || {}).value || '';
    if (!txt.trim()) { showToast('Describe the sound you want', 'error'); return; }
  }
  if (_lab.step >= 3) return;
  _lab.step++;
  document.querySelectorAll('.lab-panel').forEach(function(p) { p.classList.remove('active'); });
  document.getElementById('lab-step-' + _lab.step).classList.add('active');
  _labUpdateDots();
  if (_lab.step === 3) _labBuildPreview();
}

function labBack() {
  if (_lab.step <= 1) return;
  _lab.step--;
  document.querySelectorAll('.lab-panel').forEach(function(p) { p.classList.remove('active'); });
  document.getElementById('lab-step-' + _lab.step).classList.add('active');
  _labUpdateDots();
}

function _labBuildPrompt() {
  var parts = [];
  if (_lab.theme === 'custom') {
    parts.push((document.getElementById('lab-custom-text') || {}).value || 'ambient sleep soundscape');
  } else {
    parts.push(_labThemePrompts[_lab.theme] || 'ambient sleep soundscape');
  }
  if (_lab.apodTitle && _lab.theme === 'cosmic') {
    parts.push('Inspired by ' + _lab.apodTitle + '. ' + _lab.apodExplanation);
  }
  if (_lab.keywords.length > 0) {
    var descs = _lab.keywords.map(function(k) { return _labKeywordDescriptions[k] || k.replace('_', ' '); });
    parts.push('Featuring ' + descs.join(', '));
  }
  if (_lab.colour && _labColourDescriptions[_lab.colour]) {
    parts.push(_labColourDescriptions[_lab.colour]);
  }
  return parts.join('. ');
}

function _labBuildTitle() {
  if (_lab.theme === 'custom') return 'Custom Soundscape';
  var base = _lab.theme.charAt(0).toUpperCase() + _lab.theme.slice(1);
  if (_lab.colour) {
    var col = _lab.colour.charAt(0).toUpperCase() + _lab.colour.slice(1);
    return base + ' ' + col;
  }
  if (_lab.keywords.length > 0) {
    var first = _lab.keywords[0].replace('_', ' ');
    return base + ' ' + first.charAt(0).toUpperCase() + first.slice(1);
  }
  return base + ' Ambient';
}

function _labBuildPreview() {
  var el = document.getElementById('lab-preview-prompt');
  if (el) el.textContent = _labBuildPrompt();
}

async function labGenerate() {
  var prompt = _labBuildPrompt();
  var title = _labBuildTitle();
  var genBtns = document.getElementById('lab-gen-buttons');
  var generating = document.getElementById('lab-generating');
  var waveform = document.getElementById('lab-waveform');
  var result = document.getElementById('lab-result');

  if (genBtns) genBtns.classList.add('hidden');
  if (generating) generating.classList.remove('hidden');
  if (waveform) waveform.classList.add('generating');
  if (result) result.classList.add('hidden');

  try {
    var res = await api('/api/music/generate', 'POST', { prompt: prompt, title: title });
    if (res.error) {
      showToast(res.error, 'error');
      if (genBtns) genBtns.classList.remove('hidden');
    } else {
      showToast('Track created: ' + (res.title || title), 'success');
      if (result) {
        var resultTitle = document.getElementById('lab-result-title');
        var resultAudio = document.getElementById('lab-result-audio');
        if (resultTitle) resultTitle.textContent = res.title || title;
        if (resultAudio && res.src) { resultAudio.src = res.src; }
        result.classList.remove('hidden');
      }
      await _refreshTrackList();
    }
  } catch (e) {
    showToast('Generation failed: ' + e.message, 'error');
    if (genBtns) genBtns.classList.remove('hidden');
  } finally {
    if (generating) generating.classList.add('hidden');
    if (waveform) waveform.classList.remove('generating');
  }
}

function labUseTonight() {
  var resultAudio = document.getElementById('lab-result-audio');
  if (resultAudio && resultAudio.src) {
    var title = (document.getElementById('lab-result-title') || {}).textContent || '';
    var trackCards = document.querySelectorAll('.track-card');
    for (var i = 0; i < trackCards.length; i++) {
      if (trackCards[i].querySelector('.track-card-title') &&
          trackCards[i].querySelector('.track-card-title').textContent === title) {
        trackCards[i].click();
        break;
      }
    }
    switchTab('tonight');
    showToast('Track selected for tonight', 'success');
  }
}

// Pre-load recent sessions so they're ready when user taps Insights
(function() {
  var list = document.getElementById('recent-sessions');
  if (list) loadRecentSessions();
})();
