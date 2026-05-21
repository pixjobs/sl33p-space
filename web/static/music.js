// ───── Music Generation ─────

function _svgIcon(paths, opts) {
  opts = opts || {};
  var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('style', 'width:' + (opts.w || 15) + 'px;height:' + (opts.h || 15) + 'px');
  if (opts.fill) svg.setAttribute('fill', opts.fill);
  else svg.setAttribute('fill', 'none');
  if (opts.stroke !== false) {
    svg.setAttribute('stroke', opts.stroke || 'currentColor');
    svg.setAttribute('stroke-width', opts.strokeWidth || '2');
  }
  paths.forEach(function(p) {
    if (p.tag === 'polygon') {
      var el = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      el.setAttribute('points', p.points);
      svg.appendChild(el);
    } else {
      var el = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      el.setAttribute('d', p.d);
      svg.appendChild(el);
    }
  });
  return svg;
}

function _createTrackRow(track) {
  var row = document.createElement('div');
  row.className = 'track-row';
  row.dataset.id = track.id;
  row.dataset.src = '/media/music/' + track.filename;
  row.dataset.title = track.title;
  row.dataset.path = track.path;
  row.dataset.prompt = track.prompt || '';

  var playBtn = document.createElement('button');
  playBtn.className = 'track-play-btn';
  playBtn.title = 'Play';
  playBtn.addEventListener('click', function() { playTrack(row); });
  playBtn.appendChild(_svgIcon([{ tag: 'polygon', points: '5 3 19 12 5 21 5 3' }], { w: 14, h: 14, fill: 'currentColor', stroke: false }));
  row.appendChild(playBtn);

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

  var actions = document.createElement('div');
  actions.className = 'track-actions';

  function makeActionBtn(title, icon, handler, danger) {
    var b = document.createElement('button');
    b.className = 'track-action-btn' + (danger ? ' track-action-danger' : '');
    b.title = title;
    b.appendChild(icon);
    b.addEventListener('click', handler);
    return b;
  }

  actions.appendChild(makeActionBtn('Add to queue',
    _svgIcon([{ d: 'M12 5v14' }, { d: 'M5 12h14' }]),
    function() { addToQueue(row); }));

  actions.appendChild(makeActionBtn('Variation',
    _svgIcon([{ d: 'M12 2l1.09 3.26L16.18 6l-2.54 2.17L14.36 12 12 10.18 9.64 12l.72-3.83L7.82 6l3.09-.74z' }]),
    function() { suggestVariation(row.dataset.prompt); }));

  actions.appendChild(makeActionBtn('Archive',
    _svgIcon([{ d: 'M21 8v13H3V8' }, { d: 'M1 3h22v5H1z' }, { d: 'M10 12h4' }]),
    function() { archiveTrack(track.id); }));

  actions.appendChild(makeActionBtn('Delete',
    _svgIcon([{ d: 'M3 6h18' }, { d: 'M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2' }]),
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

// ───── Preset grid click handler ─────
var presetGrid = document.getElementById('preset-grid');
if (presetGrid) {
  presetGrid.addEventListener('click', function(e) {
    var btn = e.target.closest('.preset-btn');
    if (!btn) return;
    generateFromPreset(btn.dataset.name, btn.dataset.prompt);
  });
}
