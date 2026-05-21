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
