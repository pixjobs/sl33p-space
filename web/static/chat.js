// ───── Chat ─────

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
    up.textContent = '\u{1F44D}';
    up.title = 'Helpful';
    var down = document.createElement('button');
    down.className = 'chat-fb-btn';
    down.textContent = '\u{1F44E}';
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
