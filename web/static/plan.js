/* plan page logic */

// ───── Tabs ─────
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(function(t) { t.classList.toggle('active', t.dataset.tab === name); });
  document.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.toggle('active', p.id === 'panel-' + name); });
  if (name === 'insights') loadRecentSessions();
}

var _plan = { mood: null, track: null, trackManual: false };
var _tonightTrack = { title: null, id: null, src: null, source: 'none' };
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

      // Meta row: energy chip + factor tags (read-only display)
      var metrics = review.metrics || {};
      var energy = metrics.morning_energy;
      if (energy || factors.length > 0) {
        var metaRow = document.createElement('div');
        metaRow.className = 'recent-meta';
        if (energy) {
          var enChip = document.createElement('span');
          enChip.className = 'recent-energy-chip';
          if (energy >= 4) enChip.classList.add('fresh');
          else if (energy <= 2) enChip.classList.add('drained');
          var enLbl = ['', 'drained', 'low', 'ok', 'good', 'fresh'][energy] || '';
          enChip.textContent = '⏶ ' + enLbl;
          metaRow.appendChild(enChip);
        }
        factors.forEach(function(f) {
          var tag = document.createElement('span');
          tag.className = 'recent-tag';
          tag.textContent = f.replace(/_/g, ' ');
          metaRow.appendChild(tag);
        });
        li.appendChild(metaRow);
      }

      // Note quote (if user wrote one)
      var noteText = (review.notes || '').trim();
      if (noteText) {
        var noteEl = document.createElement('blockquote');
        noteEl.className = 'recent-note';
        noteEl.textContent = noteText;
        li.appendChild(noteEl);
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

  if (chips.length > 0 && (_tonightTrack.source !== 'manual' && _tonightTrack.source !== 'agent' && _tonightTrack.source !== 'swap' && _tonightTrack.source !== 'lab')) {
    document.querySelectorAll('.track-chip').forEach(function(c) { c.classList.remove('active'); });
    _tonightTrack = { id: chips[0].dataset.id, src: chips[0].dataset.src, title: chips[0].dataset.title, source: 'mood' };
    _plan.track = _tonightTrack;
    chips[0].classList.add('active');
    _updateTrackIndicator(_plan.track.title);
  }
}

function pickTrack(chip) {
  document.querySelectorAll('.track-chip').forEach(function(c) { c.classList.remove('active'); });
  chip.classList.add('active');
  
  var _isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
  var src = (_isSafari && chip.dataset.hlsUrl) ? chip.dataset.hlsUrl : chip.dataset.src;
  
  _tonightTrack = { id: chip.dataset.id, src: src, title: chip.dataset.title, source: 'manual' };
  _plan.track = _tonightTrack;
  _plan.trackManual = true;

  var preview = document.getElementById('track-preview');
  var title = document.getElementById('preview-title');
  preview.classList.add('visible');
  title.textContent = _plan.track.title;

  var audio = document.getElementById('preview-audio');
  audio.src = _plan.track.src;
  audio.volume = parseInt(document.getElementById('preview-vol').value) / 100;

  _updateTrackIndicator(_plan.track.title);
  var wrap = document.getElementById('use-tonight-wrap');
  if (wrap) wrap.classList.remove('hidden');
}

function _updateTrackIndicator(title) {
  var el = document.getElementById('track-indicator-title');
  if (el) el.textContent = title;
}

async function _refreshTrackList() {
  try {
    var tracks = await api('/api/music/library');
    if (!Array.isArray(tracks)) return;
    var strip = document.getElementById('track-strip');
    if (!strip) return;
    
    var uid = window._userId || '';
    
    strip.innerHTML = tracks.map(function(t) {
      var trackId = t.id || t.track_id;
      var filename = t.filename || '';
      var src = t.src || ('/media/music/' + filename);
      var hlsUrl = t.hls_url || '';
      var title = t.title || t.track_title || 'Untitled';
      var moodTags = Array.isArray(t.mood_tags) ? t.mood_tags : [];
      var energy = t.energy_level || 'low';
      var owner = (t.generated_by === uid) ? 'mine' : 'public';
      var visibility = t.visibility || 'private';
      
      var isOwner = (t.generated_by === uid);
      var ownerSpan = isOwner ? '<span class="text-[0.5rem] text-violet-400/50 ml-auto">yours</span>' : '';
      
      var visBtnClass = (visibility === 'published') 
        ? 'border-emerald-500/30 text-emerald-400/60 bg-emerald-500/5' 
        : 'border-white/10 text-white/25 bg-transparent';
      var visBtnText = (visibility === 'published') ? 'Public' : 'Private';
      var visBtnTitle = (visibility === 'published') ? 'Unpublish' : 'Publish';
      
      var visBtn = isOwner 
        ? '<button class="vis-toggle text-[0.45rem] ml-1 px-1.5 py-0.5 rounded-full border cursor-pointer transition-all ' + visBtnClass + '" data-track-id="' + trackId + '" onclick="event.stopPropagation(); toggleTrackVisibility(this)" title="' + visBtnTitle + '">' + visBtnText + '</button>' 
        : '';
        
      var tagsText = moodTags.length > 0 
        ? '<span class="block text-[0.5rem] text-white/20 mt-0.5 truncate">' + moodTags.join(' · ') + '</span>' 
        : '';
        
      return '<button class="track-chip px-3 py-2.5 bg-transparent border border-border rounded-xl cursor-pointer transition-all text-left hover:border-border-hover hover:bg-surface-hover group" ' +
             'data-id="' + trackId + '" ' +
             'data-src="' + src + '" ' +
             'data-hls-url="' + hlsUrl + '" ' +
             'data-title="' + title + '" ' +
             'data-mood-tags="' + moodTags.join(',') + '" ' +
             'data-energy="' + energy + '" ' +
             'data-owner="' + owner + '" ' +
             'data-visibility="' + visibility + '" ' +
             'onclick="pickTrack(this)">' +
             '<div class="flex items-center gap-1.5 mb-0.5">' +
             '<span class="energy-dot e-' + energy + '"></span>' +
             '<span class="text-[0.55rem] text-white/25 uppercase tracking-wider">' + energy + '</span>' +
             ownerSpan +
             visBtn +
             '</div>' +
             '<span class="block text-[0.75rem] font-medium text-white/80 group-hover:text-white truncate">' + title + '</span>' +
             tagsText +
             '</button>';
    }).join('');
    
    if (_plan.mood) _sortTracksByMood(_plan.mood);
  } catch (e) {
    console.error('Error refreshing track list:', e);
  }
}

function changeTrack() {
  switchTab('library');
}

function useTrackTonight() {
  if (!_plan.track) {
    var chips = document.querySelectorAll('.track-chip');
    if (chips.length > 0) pickTrack(chips[0]);
  }
  if (_plan.track) {
    _updateTrackIndicator(_plan.track.title);
    switchTab('tonight');
    showToast('Track selected', 'success');
  }
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
// ───── Start sleep ─────
function _resolveTrack() {
  if (_tonightTrack.source === 'manual' || _tonightTrack.source === 'agent' || _tonightTrack.source === 'swap' || _tonightTrack.source === 'lab') {
    if (_tonightTrack.id || _tonightTrack.src) return _tonightTrack;
  }
  // Fall back to the visually-selected chip (marked with .active class)
  var chips = document.querySelectorAll('.track-chip');
  for (var i = 0; i < chips.length; i++) {
    if (chips[i].classList.contains('active')) {
      return { id: chips[i].dataset.id, src: chips[i].dataset.src, title: chips[i].dataset.title };
    }
  }
  // Last resort: first chip (should rarely happen)
  if (chips.length > 0) {
    var c = chips[0];
    return { id: c.dataset.id, src: c.dataset.src, title: c.dataset.title };
  }
  return null;
}

async function startSleep() {
  var btn = document.getElementById('btn-start');
  btn.disabled = true;
  btn.textContent = 'Starting your session…';

  var preview = document.getElementById('preview-audio');
  if (preview) preview.pause();

  // Check for an existing active/planned session first to avoid duplicates
  try {
    var existing = await api('/api/sleep/current');
    if (existing && existing._id) {
      var params = new URLSearchParams();
      params.set('session', existing._id);
      if (existing.playlist_id) params.set('playlist', existing.playlist_id);
      var ePlan = existing.plan || {};
      if (ePlan.soundscape_src) params.set('track', ePlan.soundscape_src);
      if (ePlan.soundscape_title) params.set('title', ePlan.soundscape_title);
      params.set('mood', ePlan.mood || _plan.mood || 'calm');
      window.location.href = '/sleep?' + params.toString();
      return;
    }
  } catch (e) { /* no active session, proceed to create one */ }

  var track = _resolveTrack();
  console.log('[sleep] _resolveTrack →', track ? track.title + ' (' + track.id + ')' : 'null',
              '| _plan.track →', _plan.track ? _plan.track.title + ' (' + _plan.track.id + ')' : 'null');
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
  generateMusic(prompt, '');
}

// ───── Review ─────
var _reviewRating = null;
var _reviewMetrics = {};

function selectReviewRating(btn, rating) {
  _reviewRating = rating;
  document.querySelectorAll('#review-stars .review-star-btn').forEach(function(b) {
    var r = parseInt(b.dataset.rating);
    var on = r <= rating;
    b.classList.toggle('active', on);
    b.setAttribute('aria-checked', r === rating ? 'true' : 'false');
    var glyph = b.querySelector('.review-star-glyph');
    if (glyph) glyph.textContent = on ? '★' : '☆';
  });
  var submit = document.getElementById('review-submit-btn');
  if (submit) submit.disabled = false;
  var energyStep = document.getElementById('review-step-energy');
  if (energyStep) energyStep.classList.remove('hidden');
  var step2 = document.getElementById('review-step-2');
  if (step2) step2.classList.remove('hidden');
}

function expandReviewPill() {
  var pill = document.getElementById('review-pill');
  var body = document.getElementById('review-pill-body');
  var head = pill ? pill.querySelector('.review-pill-head') : null;
  if (!pill || !body) return;
  var open = pill.classList.toggle('expanded');
  body.classList.toggle('hidden', !open);
  if (head) head.setAttribute('aria-expanded', open ? 'true' : 'false');
}

function expandReviewDetail() {
  var detail = document.getElementById('review-detail');
  var toggle = document.getElementById('review-detail-toggle');
  if (!detail) return;
  var open = detail.classList.toggle('hidden');
  if (toggle) toggle.classList.toggle('open', !open);
}

function expandReviewMore() {
  var more = document.getElementById('review-more');
  var toggle = document.getElementById('review-more-toggle');
  if (!more) return;
  var open = more.classList.toggle('hidden');
  if (toggle) toggle.classList.toggle('open', !open);
}

function expandReviewNote() {
  var note = document.getElementById('review-note');
  var toggle = document.getElementById('review-note-toggle');
  if (!note) return;
  var hidden = note.classList.toggle('hidden');
  if (toggle) toggle.classList.toggle('open', !hidden);
  if (!hidden) {
    var ta = document.getElementById('review-notes');
    if (ta) setTimeout(function() { ta.focus(); }, 50);
  }
}

function appendNotePrompt(btn) {
  var ta = document.getElementById('review-notes');
  if (!ta || !btn) return;
  var text = btn.dataset.prompt || btn.textContent.trim();
  var cur = ta.value.trim();
  ta.value = cur ? cur.replace(/\.\s*$/, '') + '. ' + text + '.' : text + '.';
  btn.classList.add('used');
  ta.focus();
  var submit = document.getElementById('review-submit-btn');
  if (submit) submit.disabled = false;
}

function toggleInsightSection(id) {
  var sec = document.getElementById(id);
  if (!sec) return;
  sec.classList.toggle('collapsed');
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
    var banner = document.getElementById('review-banner') || document.getElementById('review-pill');
    if (banner) { banner.style.opacity = '0'; setTimeout(function() { banner.remove(); }, 300); }
    showToast('Review saved', 'success');
    // The coach reflects the just-reviewed night — refresh its check-in + experiment.
    if (typeof refreshCoach === 'function') refreshCoach();
  } catch (e) {
    if (btn) { btn.disabled = false; btn.textContent = 'Save'; }
    showToast('Error: ' + e.message, 'error');
  }
}

async function submitReview(sid, rating) {
  await api('/api/sleep/review', 'POST', { session_id: sid, rating: rating });
  var pill = document.getElementById('review-banner') || document.getElementById('review-pill');
  if (pill) { pill.style.opacity = '0'; setTimeout(function() { pill.remove(); }, 300); }
  showToast('Thanks!', 'success');
}

async function skipReview(sid) {
  try {
    await api('/api/sleep/review', 'POST', { session_id: sid, skip: true });
    var pill = document.getElementById('review-banner') || document.getElementById('review-pill');
    if (pill) { pill.style.opacity = '0'; setTimeout(function() { pill.remove(); }, 300); }
    // The coach strip references the pending review — refresh it so it clears.
    if (typeof refreshCoach === 'function') refreshCoach();
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
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
  var data = await api('/api/sleep/end', 'POST', { session_id: sid });
  var banner = document.getElementById('active-session-banner');
  if (banner) { banner.style.opacity = '0'; setTimeout(function() { banner.remove(); }, 300); }
  if (data && data.chat_bonus > 0) {
    showToast('Good sleep! +' + data.chat_bonus + ' chat messages earned', 'success', 5000);
  } else {
    showToast('Session ended', 'success');
  }
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

// ───── Track visibility toggle ─────
async function toggleTrackVisibility(btn) {
  var trackId = btn.dataset.trackId;
  var chip = btn.closest('.track-chip');
  var current = chip.dataset.visibility;
  var next = current === 'published' ? 'private' : 'published';
  try {
    await api('/api/music/' + trackId + '/visibility', { method: 'POST', body: JSON.stringify({ visibility: next }) });
    chip.dataset.visibility = next;
    btn.textContent = next === 'published' ? 'Public' : 'Private';
    btn.title = next === 'published' ? 'Unpublish' : 'Publish';
    if (next === 'published') {
      btn.className = btn.className.replace(/border-white\/10 text-white\/25 bg-transparent/, 'border-emerald-500/30 text-emerald-400/60 bg-emerald-500/5');
    } else {
      btn.className = btn.className.replace(/border-emerald-500\/30 text-emerald-400\/60 bg-emerald-500\/5/, 'border-white/10 text-white/25 bg-transparent');
    }
    showToast(next === 'published' ? 'Track published to community' : 'Track set to private', 'success');
  } catch (e) {
    showToast('Could not update visibility', 'error');
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
function _el(tag, cls, txt) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt != null) e.textContent = txt;
  return e;
}

function _renderAgentRec(data) {
  var loading = document.getElementById('agent-rec-loading');
  var content = document.getElementById('agent-rec-content');
  var empty = document.getElementById('agent-rec-empty');
  if (loading) loading.classList.add('hidden');

  if (_tonightTrack.source === 'none') {
    var recMood = (data && data.mood) || (document.getElementById('plan-card') || {}).dataset.recommendedMood || 'calm';
    var btn = document.querySelector('.mood-btn[data-mood="' + recMood + '"]') || document.querySelector('.mood-btn[data-mood="calm"]');
    if (btn) pickMood(btn);
  }

  if (!data || !data.reasoning) {
    if (empty) empty.classList.remove('hidden');
    return;
  }

  _agentRec = data;

  var vibe = document.getElementById('agent-vibe');
  if (vibe) {
    if (data.vibe) {
      vibe.textContent = '“' + data.vibe + '”';
      vibe.classList.remove('hidden');
    } else {
      vibe.classList.add('hidden');
    }
  }

  var text = document.getElementById('agent-rec-text');
  if (text) {
    text.textContent = data.reasoning + (data.soundscape_title ? ' — ' + data.soundscape_title : '');
  }

  _renderMission(data.mission || []);

  // Fill the live MongoDB MCP verification step after render (off the
  // page-load path, so the page never hangs on the MCP turn).
  if (data.soundscape_title) _runMcpVerify(data.soundscape_title, data.mood || 'calm');

  var ring = document.getElementById('agent-conf-ring');
  if (ring) _renderConfidenceRing(ring, data.confidence);

  var meta = document.getElementById('agent-meta');
  if (meta) {
    var bits = [];
    if (data.predicted_outcome) bits.push(data.predicted_outcome);
    if (data.source) bits.push(data.source === 'gemini' ? 'Gemini 3 + MongoDB' : 'MongoDB');
    if (bits.length) {
      meta.textContent = bits.join(' · ');
      meta.classList.remove('hidden');
    } else {
      meta.classList.add('hidden');
    }
  }

  if (content) content.classList.remove('hidden');
}

// Render the mission steps, revealing them one-by-one so the agent visibly
// "works through" the plan rather than dumping a finished list.
function _renderMission(steps) {
  var ol = document.getElementById('agent-mission');
  if (!ol) return;
  ol.replaceChildren();
  if (!Array.isArray(steps) || !steps.length) { ol.classList.add('hidden'); return; }
  ol.classList.remove('hidden');

  steps.forEach(function(s, i) {
    var li = _missionStepEl(s);
    li.style.setProperty('--i', i);
    ol.appendChild(li);
    // Sequential reveal for the "watch it work" feel.
    setTimeout(function() { li.classList.add('revealed'); }, 160 * i + 80);
  });
}

// Build one mission step <li>. Reused for live updates (e.g. MCP verify).
function _missionStepEl(s) {
  var li = _el('li', 'mission-step status-' + (s.status || 'done'));
  if (s.mcp_tool) li.classList.add('is-mcp');
  if (s.key) li.dataset.key = s.key;
  li.appendChild(_el('span', 'mission-icon'));
  var body = _el('span', 'mission-body');
  var head = _el('span', 'mission-title', s.title || '');
  if (s.tool === 'MongoDB' || s.mcp_tool) {
    var badge = _el('span', 'agent-trace-mcp-badge', s.mcp_tool ? 'MCP' : 'MongoDB');
    if (s.mcp_query) badge.title = s.mcp_tool + ' — ' + s.mcp_query;
    head.appendChild(badge);
  }
  body.appendChild(head);
  if (s.detail) body.appendChild(_el('span', 'mission-detail', s.detail));
  if (s.mcp_query) body.appendChild(_el('span', 'agent-trace-mcp-query', s.mcp_query));
  li.appendChild(body);
  return li;
}

// Live MongoDB MCP verification: show a "verifying" step, then fill it in (or
// drop it if MCP isn't available, e.g. locally without the MCP server).
function _runMcpVerify(track, mood) {
  var ol = document.getElementById('agent-mission');
  if (!ol) return;
  var pending = _missionStepEl({
    key: 'verify', status: 'pending',
    title: 'Verifying against MongoDB (MCP)…',
    detail: 'Querying the live database',
  });
  pending.classList.add('revealed');
  // Insert right after the history-analysis step.
  var first = ol.querySelector('.mission-step[data-key="analyse"]') || ol.firstChild;
  if (first && first.nextSibling) ol.insertBefore(pending, first.nextSibling);
  else ol.appendChild(pending);

  var timer = setTimeout(function() {
    pending.textContent = 'Using deterministic data (MCP unavailable)';
    pending.classList.add('revealed');
    // Remove after 2s to keep the UI clean
    setTimeout(function() { pending.remove(); }, 2000);
  }, 12000);

  api('/api/agent/verify', 'POST', { track: track, mood: mood }).then(function(v) {
    clearTimeout(timer);
    if (!v || !v.mcp_used) { pending.remove(); return; }
    var avg = v.avg_rating, cnt = v.sessions_count || 0;
    var detail = (avg != null && cnt) ? (avg + '/5 across ' + cnt + ' matching nights — confirms the pick')
               : (cnt ? (cnt + ' matching nights in the live database')
                      : 'no prior nights for this pairing — flagged as exploration');
    var done = _missionStepEl({
      key: 'verify', status: 'done', mcp_tool: v.mcp_tool, mcp_query: v.mcp_query,
      title: 'Verified against MongoDB', detail: detail,
    });
    done.classList.add('revealed');
    ol.replaceChild(done, pending);
  }).catch(function() { 
    clearTimeout(timer);
    pending.remove(); 
  });
}

function _renderConfidenceRing(el, confidence) {
  var pct = (typeof confidence === 'number') ? Math.max(0, Math.min(1, confidence)) : 0;
  var deg = Math.round(pct * 360);
  var hue = 150; // MongoDB green-ish for high confidence
  el.style.background =
    'conic-gradient(hsl(' + hue + ' 80% 55%) ' + deg + 'deg, rgba(255,255,255,0.08) ' + deg + 'deg)';
  el.replaceChildren();
  var inner = _el('span', 'conf-ring-inner');
  inner.appendChild(_el('strong', 'conf-ring-pct', Math.round(pct * 100) + '%'));
  inner.appendChild(_el('span', 'conf-ring-label', 'confidence'));
  el.appendChild(inner);
}

(function() {
  var recCard = document.getElementById('agent-card');
  if (!recCard) return;
  (async function() {
    try {
      var data = await api('/api/sleep/recommend', 'POST', { mood: _plan.mood || 'calm' });
      _renderAgentRec(data);
    } catch (e) {
      _renderAgentRec(null);
    }
  })();
})();

// ───── Coach check-in + multi-night experiment ─────
(function() {
  if (document.getElementById('coach-strip')) refreshCoach();
})();

function refreshCoach() {
  api('/api/coach').then(renderCoach).catch(function() {});
}

function renderCoach(data) {
  if (!data) return;
  var strip = document.getElementById('coach-strip');
  var line = document.getElementById('coach-line');
  var avatar = document.getElementById('coach-avatar');
  if (strip && line && data.checkin) {
    line.textContent = data.checkin.message || '';
    if (avatar) avatar.textContent = (data.checkin.coach || 'N').charAt(0);
    strip.classList.remove('hidden');
  }
  var mount = document.getElementById('experiment-mount');
  if (!mount) return;
  mount.replaceChildren();
  var exp = data.experiment || {};
  if (exp.completed) mount.appendChild(_expCompletedCard(exp.completed));
  if (exp.active) mount.appendChild(_expActiveCard(exp.active));
  else if (exp.proposed) mount.appendChild(_expProposedCard(exp.proposed));
}

function _expCard() {
  var c = _el('section', 'exp-card');
  var head = _el('div', 'exp-card-head');
  head.appendChild(_el('span', 'exp-badge', 'Experiment'));
  c.appendChild(head);
  return { card: c, head: head };
}

function _expProposedCard(p) {
  var b = _expCard();
  b.head.appendChild(_el('span', 'exp-card-title', p.hypothesis || 'Try an experiment'));
  if (p.detail) b.card.appendChild(_el('p', 'exp-detail', p.detail));
  b.card.appendChild(_el('p', 'exp-ask',
    'Run a ' + (p.target_nights || 3) + '-night test and I’ll measure the difference?'));
  var actions = _el('div', 'exp-actions');
  var yes = _el('button', 'btn btn-sm btn-primary rounded-lg', 'Start the test');
  yes.onclick = function() { acceptExperiment(p.factor); };
  var no = _el('button', 'btn btn-sm btn-ghost rounded-lg', 'Not now');
  no.onclick = function() { declineExperiment(p.factor); };
  actions.appendChild(yes); actions.appendChild(no);
  b.card.appendChild(actions);
  return b.card;
}

function _expActiveCard(a) {
  var b = _expCard();
  b.head.appendChild(_el('span', 'exp-card-title', 'Avoiding ' + (a.label || 'a factor')));
  var target = a.target_nights || 3;
  var done = (a.nights || []).filter(function(n) { return n.adhered; }).length;
  var dots = _el('div', 'exp-dots');
  for (var i = 0; i < target; i++) {
    dots.appendChild(_el('span', 'exp-dot' + (i < done ? ' filled' : '')));
  }
  b.card.appendChild(dots);
  b.card.appendChild(_el('p', 'exp-detail',
    done + ' of ' + target + ' nights logged · rate tonight to keep it going'));
  return b.card;
}

function _expCompletedCard(c) {
  var b = _expCard();
  b.head.appendChild(_el('span', 'exp-card-title', 'Experiment result'));
  var res = c.result || {};
  b.card.classList.add('exp-done');
  b.card.appendChild(_el('p', 'exp-conclusion', res.conclusion || 'Experiment complete.'));
  var actions = _el('div', 'exp-actions');
  var ok = _el('button', 'btn btn-sm btn-ghost rounded-lg', 'Got it');
  ok.onclick = function() { ackExperiment(c._id); };
  actions.appendChild(ok);
  b.card.appendChild(actions);
  return b.card;
}

function acceptExperiment(factor) {
  api('/api/coach/experiment/accept', 'POST', { factor: factor })
    .then(function() { showToast('Experiment started', 'success'); refreshCoach(); })
    .catch(function() { showToast('Could not start experiment', 'error'); });
}

function declineExperiment(factor) {
  api('/api/coach/experiment/decline', 'POST', { factor: factor })
    .then(function() { refreshCoach(); }).catch(function() {});
}

function ackExperiment(id) {
  api('/api/coach/experiment/ack', 'POST', { id: id })
    .then(function() { refreshCoach(); }).catch(function() {});
}

// Apply the agent's chosen track to the plan card. Returns true if applied.
function _applyAgentTrack() {
  if (!_agentRec || !_agentRec.soundscape_title) return false;
  var chips = document.querySelectorAll('.track-chip');
  for (var i = 0; i < chips.length; i++) {
    if (chips[i].dataset.title === _agentRec.soundscape_title) {
      pickTrack(chips[i]);
      _tonightTrack = { title: _agentRec.soundscape_title, id: chips[i].dataset.id, src: chips[i].dataset.src, source: 'agent' };
      _plan.track = _tonightTrack;
      _updateTrackIndicator(_agentRec.soundscape_title);
      return true;
    }
  }
  _tonightTrack = { title: _agentRec.soundscape_title, id: null, src: null, source: 'agent' };
  _plan.track = _tonightTrack;
  _updateTrackIndicator(_agentRec.soundscape_title);
  return true;
}

// Approve & start — the agent executes the final mission step on the user's nod.
function useAgentPlan() {
  if (!_agentRec) return;
  _applyAgentTrack();
  var ready = document.querySelector('#agent-mission .mission-step.status-await');
  if (ready) ready.classList.add('status-done');
  startSleep();
}

// Keep the user in control: cycle the chosen track through the candidates the
// agent surfaced, updating the mission's "chose" step in place.
function swapAgentTrack() {
  if (!_agentRec) return;
  var opts = _agentRec.available_tracks || [];
  if (opts.length < 2) { showToast('No other tracks to swap to', 'info'); return; }
  var cur = _agentRec.soundscape_title;
  var idx = opts.indexOf(cur);
  var next = opts[(idx + 1) % opts.length];
  _agentRec.soundscape_title = next;
  _tonightTrack = { title: next, source: 'swap', id: null, src: null };  // ← mark as swapped
  _plan.track = _tonightTrack;
  _applyAgentTrack();
  // Update the mission's "chose" step detail in place.
  var steps = document.querySelectorAll('#agent-mission .mission-step .mission-detail');
  (_agentRec.mission || []).forEach(function(s, i) {
    if (s.key === 'choose' && steps[i]) {
      steps[i].textContent = next + ' — swapped by you';
    }
  });
  var text = document.getElementById('agent-rec-text');
  if (text) text.textContent = 'Swapped to ' + next + ' — your call.';
  showToast('Swapped to ' + next, 'success');
}

// Re-run the whole mission from scratch.
function regenerateAgentPlan() {
  var loading = document.getElementById('agent-rec-loading');
  var content = document.getElementById('agent-rec-content');
  if (content) content.classList.add('hidden');
  if (loading) loading.classList.remove('hidden');
  api('/api/sleep/recommend', 'POST', { mood: _plan.mood || 'calm' })
    .then(function(data) { _renderAgentRec(data); })
    .catch(function() { _renderAgentRec(null); });
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
        _updateApodCredit(img);
      };
      preload.src = img.url;
    }
  }).catch(function() {});
})();

function _updateApodCredit(img) {
  if (!img) return;
  var box = document.getElementById('apod-credit');
  var t = document.getElementById('apod-credit-title');
  var m = document.getElementById('apod-credit-meta');
  if (!box) return;
  if (t) t.textContent = img.title || '';
  if (m) {
    var who = img.copyright ? String(img.copyright).replace(/\s+/g, ' ').trim() : 'Public Domain';
    m.textContent = '© ' + who + ' · NASA APOD';
  }
  box.hidden = false;
}

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

function toggleLabWizard() {
  var wizard = document.getElementById('lab-wizard');
  var btn = document.getElementById('lab-create-btn');
  if (!wizard) return;
  var show = wizard.classList.contains('hidden');
  wizard.classList.toggle('hidden', !show);
  if (btn) btn.classList.toggle('hidden', show);
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
      _labResetGenUI(genBtns, generating, waveform);
      return;
    }
    if (res.job_id) {
      showToast('Generating your track — this takes about a minute...', 'info', 15000);
      _labPollJob(res.job_id, genBtns, generating, waveform, result);
      return;
    }
    _labShowResult(res, result);
    _labResetGenUI(genBtns, generating, waveform);
    await _refreshTrackList();
  } catch (e) {
    showToast('Generation failed: ' + e.message, 'error');
    _labResetGenUI(genBtns, generating, waveform);
  }
}

function _labResetGenUI(genBtns, generating, waveform) {
  if (genBtns) genBtns.classList.remove('hidden');
  if (generating) generating.classList.add('hidden');
  if (waveform) waveform.classList.remove('generating');
}

function _labShowResult(res, resultEl) {
  showToast('Track created: ' + (res.title || 'New track'), 'success');
  if (resultEl) {
    var resultTitle = document.getElementById('lab-result-title');
    var resultAudio = document.getElementById('lab-result-audio');
    if (resultTitle) resultTitle.textContent = res.title || '';
    if (resultAudio && res.src) { resultAudio.src = res.src; }
    resultEl.classList.remove('hidden');
  }
}

async function _labPollJob(jobId, genBtns, generating, waveform, resultEl) {
  for (var i = 0; i < 60; i++) {
    await new Promise(function(r) { setTimeout(r, 5000); });
    try {
      var job = await api('/api/music/job/' + jobId);
      if (job.status === 'complete') {
        _labShowResult(job.result || {}, resultEl);
        _labResetGenUI(genBtns, generating, waveform);
        await _refreshTrackList();
        return;
      }
      if (job.status === 'failed') {
        showToast((job.result || {}).error || 'Generation failed', 'error');
        _labResetGenUI(genBtns, generating, waveform);
        return;
      }
    } catch (e) { /* keep polling */ }
  }
  showToast('Generation is taking longer than expected. Check your library later.', 'info');
  _labResetGenUI(genBtns, generating, waveform);
}

function labUseTonight() {
  var resultAudio = document.getElementById('lab-result-audio');
  if (resultAudio && resultAudio.src) {
    var title = (document.getElementById('lab-result-title') || {}).textContent || '';
    var found = false;
    var chips = document.querySelectorAll('.track-chip');
    for (var i = 0; i < chips.length; i++) {
      if (chips[i].dataset.title === title) {
        pickTrack(chips[i]);
        _tonightTrack.source = 'lab';
        _plan.track = _tonightTrack;
        found = true;
        break;
      }
    }
    if (!found) {
      _tonightTrack = { title: title, id: null, src: resultAudio.src, source: 'lab' };
      _plan.track = _tonightTrack;
    }
    _updateTrackIndicator(title);
    switchTab('tonight');
    showToast('Track selected for tonight', 'success');
  }
}

// Pre-load recent sessions so they're ready when user taps Insights
(function() {
  var list = document.getElementById('recent-sessions');
  if (list) loadRecentSessions();
})();
