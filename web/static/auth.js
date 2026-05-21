// ───── Authentication (Firebase + GSI) ─────

var _justSignedOut = window.location.search.indexOf('signed_out') !== -1;

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
        if (window.location.pathname === '/' && !_justSignedOut) {
          _showAuthLoading();
          window.location.href = '/plan';
          return;
        }
        _justSignedOut = false;
        var tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        if (tz) api('/api/user/timezone', 'POST', { timezone: tz });
        var refCode = localStorage.getItem('sl33p_ref');
        if (refCode) {
          localStorage.removeItem('sl33p_ref');
          api('/api/user/redeem-referral', 'POST', { code: refCode }).then(function(res) {
            if (res && res.status === 'ok') showToast('Referral bonus: +1 credit!', 'success');
          });
        }
      }).catch(function() {
        _hideAuthLoading();
        _signOutAndGoHome();
      });
      if (signInBtn) signInBtn.style.display = 'none';
      if (userInfo) userInfo.style.display = '';
      if (avatar) { avatar.src = user.photoURL || ''; avatar.style.display = user.photoURL ? '' : 'none'; }
      if (username) username.textContent = user.displayName || user.email || '';
    } else {
      _authToken = null;
      if (signInBtn) signInBtn.style.display = '';
      if (userInfo) userInfo.style.display = 'none';
      // Firebase lost auth state but Flask session may still exist (common on
      // Chrome iOS where WKWebView clears IndexedDB). Clear the stale Flask
      // session and redirect to login if we're on a protected page.
      var p = window.location.pathname;
      if (p !== '/' && p !== '/about' && p !== '/privacy' && p !== '/terms') {
        fetch('/api/auth/signout', { method: 'POST', credentials: 'same-origin' }).catch(function() {}).finally(function() {
          document.cookie = 'session=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/;';
          window.location.replace('/?signed_out=1');
        });
      }
    }
  });

  setInterval(function() {
    var user = firebase.auth().currentUser;
    if (user) {
      user.getIdToken(true).then(function(token) {
        _authToken = token;
      }).catch(function() {
        _signOutAndGoHome();
      });
    }
  }, 10 * 60 * 1000);
}

function _signOutAndGoHome() {
  _authToken = null;
  var fbDone = Promise.resolve();
  try { fbDone = firebase.auth().signOut(); } catch (e) {}
  Promise.all([
    fbDone,
    fetch('/api/auth/signout', { method: 'POST', credentials: 'same-origin' }).catch(function() {})
  ]).finally(function() {
    document.cookie = 'session=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/;';
    var p = window.location.pathname;
    if (p !== '/' && p !== '/about' && p !== '/privacy' && p !== '/terms') {
      window.location.replace('/?signed_out=1');
    }
  });
}

// ───── Auth Loading Overlay ─────

function _showAuthLoading(msg) {
  if (document.getElementById('auth-loading-overlay')) return;
  var overlay = document.createElement('div');
  overlay.id = 'auth-loading-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(8,9,13,0.85);backdrop-filter:blur(8px);transition:opacity 0.2s;';
  var inner = document.createElement('div');
  inner.style.cssText = 'text-align:center;';
  var spinner = document.createElement('div');
  spinner.style.cssText = 'width:32px;height:32px;border:2.5px solid rgba(124,92,252,0.2);border-top-color:#7c5cfc;border-radius:50%;animation:spin .6s linear infinite;margin:0 auto 12px;';
  var label = document.createElement('div');
  label.style.cssText = 'color:rgba(255,255,255,0.5);font-size:0.8rem;font-family:Inter,system-ui,sans-serif;';
  label.textContent = msg || 'Signing in…';
  inner.appendChild(spinner);
  inner.appendChild(label);
  overlay.appendChild(inner);
  if (!document.getElementById('auth-spin-style')) {
    var style = document.createElement('style');
    style.id = 'auth-spin-style';
    style.textContent = '@keyframes spin{to{transform:rotate(360deg)}}';
    document.head.appendChild(style);
  }
  document.body.appendChild(overlay);
}

function _hideAuthLoading() {
  var el = document.getElementById('auth-loading-overlay');
  if (el) el.remove();
}

// ───── Google Sign-In (GSI) ─────

var _gsiInitialized = false;

function _ensureGsi(cb) {
  if (!window.__firebaseConfig || !window.__googleClientId) return;
  if (!window.google || !window.google.accounts || !window.google.accounts.id) {
    showToast('Google sign-in is loading, please try again', 'info');
    return;
  }
  if (!_gsiInitialized) {
    google.accounts.id.initialize({
      client_id: window.__googleClientId,
      callback: _handleGsiCredential,
      ux_mode: 'popup',
      auto_select: false,
      cancel_on_tap_outside: true,
      itp_support: true
    });
    _gsiInitialized = true;
  }
  if (cb) cb();
}

function signInWithGoogle() {
  _justSignedOut = false;
  _ensureGsi(function() {
    google.accounts.id.prompt(function(notification) {
      if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
        _gsiButtonFallback();
      }
    });
  });
}

function _handleGsiCredential(response) {
  _showAuthLoading();
  var credential = firebase.auth.GoogleAuthProvider.credential(response.credential);
  firebase.auth().signInWithCredential(credential).catch(function(err) {
    _hideAuthLoading();
    showToast('Sign-in failed: ' + err.message, 'error');
  });
}

function _gsiButtonFallback() {
  var target = document.getElementById('gsi-button-fallback');
  if (!target) {
    var authBtns = document.getElementById('auth-buttons');
    if (!authBtns) return;
    target = document.createElement('div');
    target.id = 'gsi-button-fallback';
    target.style.cssText = 'display:flex;justify-content:center;margin-top:8px;';
    var existingBtn = authBtns.querySelector('button');
    if (existingBtn) existingBtn.style.display = 'none';
    authBtns.insertBefore(target, authBtns.firstChild);
  }
  google.accounts.id.renderButton(target, {
    type: 'standard',
    theme: 'filled_black',
    size: 'large',
    width: 320,
    text: 'continue_with',
    shape: 'pill'
  });
}

// ───── Email Auth ─────

function signInWithEmail(email, password) {
  if (!window.__firebaseConfig) return;
  _justSignedOut = false;
  var errEl = document.getElementById('auth-error');
  if (errEl) { errEl.textContent = ''; errEl.style.display = 'none'; }
  _showAuthLoading();
  firebase.auth().signInWithEmailAndPassword(email, password).catch(function(err) {
    _hideAuthLoading();
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
  _showAuthLoading('Signing out…');
  _authToken = null;
  var fbDone = Promise.resolve();
  if (window.__firebaseConfig) {
    try { fbDone = firebase.auth().signOut(); } catch (e) {}
  }
  Promise.all([
    fbDone,
    fetch('/api/auth/signout', { method: 'POST', credentials: 'same-origin' })
  ]).finally(function() {
    document.cookie = 'session=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/;';
    window.location.replace('/?signed_out=1');
  });
}
