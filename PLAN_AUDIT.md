# sl33p-space — Audit & Fix Plan

## Context

This is the "Tonight" tab on `/plan`. The user:
1. Sees a mood selector + track strip + "Start Sleep" button.
2. The agent card fires `/api/sleep/recommend` on page load and proposes a track.
3. User can change mood, manually pick a track, approve agent's track, swap, or regenerate.
4. "Start Sleep" creates a session + playlist, navigates to `/sleep`.
5. Next morning: review banner appears → user rates night → factors → session marked "reviewed".
6. Experiments: coach proposes a factor experiment → user accepts → each reviewed night counts as adhered/not-adhered → auto-completes after N nights → result reported.

---

## Bugs Found (in severity order)

### BUG-1 (Critical): Experiment data destroyed on "Skip Review"

**File:** `web/static/plan.js:566-576`, `web/app.py:787-793`

`skipReview()` calls `api('/api/delete', …)` which **deletes the entire session document** from MongoDB. This destroys all data the experiment needs (rating, factors, adherence tracking). A user who skips a review effectively erases their session from experiment calculations.

**Fix:** `skipReview()` should call `POST /api/sleep/review` with `{ skip: true, session_id: sid }` instead of deleting the session.

---

### BUG-2 (Critical): `_resolveTrack()` returns wrong track after mood change

**File:** `web/static/plan.js:340-356`

Flow:
1. Page loads → `_plan.track` set to first chip (with `id`).
2. User clicks mood "wired" → `_sortTracksByMood()` clears all `.active` chips and sets `_plan.track = { id: chips[0].id, … }` where chips[0] is now the first **reordered** chip. `_plan.trackManual = false`.
3. User clicks mood back to "calm" → chips reorder again, `_plan.track` updated again.
4. User clicks "Approve & start" → `useAgentPlan()` calls `_applyAgentTrack()` which tries to find the agent's track by title among chips. If the agent's track title doesn't match any chip (or chip reordered away), `_applyAgentTrack()` returns `true` but only updates the indicator text — it does NOT set `_plan.track`.
5. `startSleep()` → `_resolveTrack()` checks `_plan.track && _plan.track.id` — this passes because the last mood-set `_plan.track` has an `id`. But the track ID might belong to a chip the user never intended.
6. Worse: if `_plan.trackManual` is true (user manually clicked a chip), then picked a different mood, `_plan.trackManual` stays true but `_plan.track` gets overwritten by `_sortTracksByMood()`.

**Root cause:** `_plan.track` and the DOM `.active` state get out of sync whenever mood changes or agent swaps. There's no single source of truth.

**Fix:** See FIX-2 below.

---

### BUG-3 (High): `_plan.mood` silently set to `'calm'` on load, overwriting agent recommendation

**File:** `web/static/plan.js:330-337`

```js
(function() {
  var card = document.getElementById('plan-card');
  if (!card) return;
  var mood = card.dataset.recommendedMood || 'calm';  // ← always 'calm' as fallback
  var btn = document.querySelector('.mood-btn[data-mood="' + mood + '"]');
  if (btn) pickMood(btn);  // ← sets _plan.mood = mood, reorders chips
})();
```

`plan-card` has `data-recommended-mood="{{ insights.recommended_mood }}"`. When `insights.available` is false or insights are empty, this defaults to `calm` and calls `pickMood()` which reorders all chips. But the agent recommendation call at line 904 also uses `_plan.mood || 'calm'` — so by the time the API returns, `_plan.mood` is already set to the server-recommended mood.

The problem: the IIFE runs before the agent rec API call completes. If the agent recommends mood "wired" and `_plan.mood` was initially `null`, the IIFE sets it to "calm" (from the card), then the API call at line 904 uses "calm" to build the recommendation, **never asking the agent for a "wired" recommendation even though the user might be wired**.

**Fix:** Defer the mood button auto-selection until after the agent rec loads, or remove the initial call entirely and let the agent's mood be authoritative.

---

### BUG-4 (High): Swap track only cycles by title — can swap to wrong track or silently fail

**File:** `web/static/plan.js:1035-1054`

```js
function swapAgentTrack() {
  var opts = _agentRec.available_tracks || [];  // ← server-side titles
  var cur = _agentRec.soundscape_title;
  var idx = opts.indexOf(cur);
  var next = opts[(idx + 1) % opts.length];
  _agentRec.soundscape_title = next;          // ← mutates stale reference
  _applyAgentTrack();                          // ← may silently do nothing
  // … updates mission DOM by index match, not by key
}
```

`_agentRec.available_tracks` is an array of track titles from the server. `swapAgentTrack()` cycles through them. But:
- The chip list may not contain all these tracks (tracks can be deleted, archived, or not yet loaded).
- `_applyAgentTrack()` only highlights a chip if its `data-title` matches — if no chip matches, it just updates the indicator text with the new title but no chip is active.
- `_plan.track` is never updated, so `startSleep()` will use whatever `_plan.track` currently holds (which may be the old track or a mismatched mood-selected track).

**Fix:** `swapAgentTrack()` should call the server for a fresh recommendation (or a new endpoint) instead of client-side cycling.

---

### BUG-5 (Medium): `_refreshTrackList` is referenced but not defined

**File:** `web/static/plan.js:701, 706, 1300, 1332`

`_refreshTrackList()` is called in 4 places (seeding poll after seed complete, lab generate success, lab poll complete) but there is no function definition for it anywhere in `plan.js`. This means:
- After track generation completes, the strip is **never updated** with the new track.
- The user sees a stale chip list.
- `labUseTonight()` tries to find the newly generated track by title among chips — fails because the chip was never added.
- Seeding poll calls `_refreshTrackList()` after server confirms 5+ tracks — silently fails.

**Fix:** Define `_refreshTrackList()` to re-render chips from the server, or inline the chip rendering logic where it's called.

---

### BUG-6 (Medium): Agent rec page-load hangs on MCP verification

**File:** `web/static/plan.js:857-884`

`_runMcpVerify()` fires after agent rec renders, but if the MCP server is slow or unavailable, the "Verifying…" step stays pending indefinitely (no timeout). The step is only removed on success or error callback — but the error callback is `catch(function() { pending.remove(); })`. If the API succeeds but returns `{ mcp_used: false }`, the step is removed (good). But if the API takes > 30s, the user sees a stuck "Verifying…" step forever.

**Fix:** Add a 12-second timeout. After timeout, either drop the step or show "MCP unavailable — using deterministic data".

---

### BUG-7 (Medium): Coach check-in can show duplicate/conflicting messages

**File:** `agent/agent.py:879-897`

```python
parts = []
if completed and completed.get("result"):
    parts.append(completed["result"]["conclusion"])  # "Experiment done — cutting X helped"
if pending:
    parts.append("… how did last night treat you?")   # "Rate tonight's plan"
elif active:
    parts.append("… stay with it tonight.")            # Experiment progress
elif memories:
    parts.append("Last time: …")
```

If both `completed` (from a recently finished experiment) AND `pending` (a session waiting review) exist, both messages are concatenated with a space. The user sees:

> "Cutting screens helped — 3.8/5 versus 2.9/5. Worth keeping up. Morning — how did last night treat you? A quick rating sharpens tonight's plan."

That's a lot of text for a strip. Also: `completed` is checked first, so even if there's an active experiment in progress, the old completed result shows instead.

**Fix:** Priority should be: (1) active experiment progress, (2) pending review, (3) completed experiment result, (4) memory. Also truncate/shorten for the strip.

---

### BUG-8 (Low): `_build_prompt` experiment section has stale `active` state

**File:** `agent/agent.py:926-936`

The prompt injected into the chat agent references `get_active_experiment()`. If the experiment was just completed (status changed to "completed" by `record_experiment_night`), the prompt won't reference it — which is correct. But there's a race: if the user reviews a night and the experiment completes mid-session, the next chat turn won't know about the completion until the next page load.

**Minor:** Not a critical bug, but worth noting for consistency.

---

### BUG-9 (Low): Review factors on recent-sessions list are read-only; can't add factors to unreviewed sessions

**File:** `web/static/plan.js:152-168`

The factor editor in recent sessions shows `toggleFactor` for all sessions with `_id`, but it only sends factors to `/api/sleep/factors`. If the session hasn't been reviewed yet (status != "completed"/"reviewed"), `update_session_factors()` returns `False` (line 351 in `sessions.py`: `if session["status"] not in ("completed", "reviewed"): return False`).

**Fix:** Allow factor editing for "planned" sessions too, or document that factors can only be added post-review.

---

## Detailed Fixes

### FIX-1: `skipReview()` → use review API, not delete

**File:** `web/static/plan.js`, function `skipReview`

**Before:**
```js
async function skipReview(sid) {
  try {
    await api('/api/sleep/delete', 'POST', { session_id: sid });
    // …remove banner…
  } catch (e) { /* … */ }
}
```

**After:**
```js
async function skipReview(sid) {
  try {
    await api('/api/sleep/review', 'POST', { session_id: sid, skip: true });
    var pill = document.getElementById('review-pill');
    if (pill) { pill.style.opacity = '0'; setTimeout(function() { pill.remove(); }, 300); }
    if (typeof refreshCoach === 'function') refreshCoach();
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
}
```

---

### FIX-2: Introduce a single-source-of-truth for the "tonight's track"

**File:** `web/static/plan.js`

Add a new tracking variable and fix all code paths:

```js
// New: tracks the user's intentional choice vs. the system default
var _tonightTrack = { title: null, id: null, src: null, source: 'none' };
// 'none' = nothing picked yet
// 'agent' = agent's recommendation applied via useAgentPlan()
// 'manual' = user clicked a chip
// 'mood' = auto-selected when mood changed
```

Update `_resolveTrack()` to prefer `_tonightTrack`:
```js
function _resolveTrack() {
  if (_tonightTrack.source === 'manual' || _tonightTrack.source === 'agent') {
    if (_tonightTrack.id) return _tonightTrack;
  }
  // Fallback: active chip
  var chips = document.querySelectorAll('.track-chip');
  var active = document.querySelector('.track-chip.active');
  if (active) return { id: active.dataset.id, src: active.dataset.src, title: active.dataset.title };
  if (chips.length > 0) {
    var c = chips[0];
    return { id: c.dataset.id, src: c.dataset.src, title: c.dataset.title };
  }
  return null;
}
```

Update `pickTrack()` to set `_tonightTrack.source = 'manual'`.

Update `_sortTracksByMood()` to set `_tonightTrack.source = 'mood'`.

Update `_applyAgentTrack()` to set `_tonightTrack.source = 'agent'` and update `_tonightTrack`.

Update `useAgentPlan()` to set `_tonightTrack.source = 'agent'`.

Update `swapAgentTrack()` to update `_tonightTrack.source = 'swap'` after applying.

Update `labUseTonight()` to set `_tonightTrack.source = 'lab'` after applying.

---

### FIX-3: Defer mood auto-selection until after agent rec

**File:** `web/static/plan.js`

Remove the initial mood-selection IIFE (lines 330-337). Instead, in `_renderAgentRec()` after receiving the agent's recommendation, if no mood has been manually picked (`_plan.trackManual === false` AND `_tonightTrack.source === 'none'`), call `pickMood()` with the agent's mood.

This ensures the agent's mood recommendation is authoritative and the mood-only chips are sorted based on the correct mood.

---

### FIX-4: Replace client-side track cycling with server call

**File:** `web/static/plan.js`, function `swapAgentTrack()`

**Before:**
```js
function swapAgentTrack() {
  var opts = _agentRec.available_tracks || [];
  // …cycle by index…
}
```

**After:**
```js
async function swapAgentTrack() {
  if (!_agentRec) return;
  var opts = _agentRec.available_tracks || [];
  if (opts.length < 2) { showToast('No other tracks to swap to', 'info'); return; }
  var cur = _agentRec.soundscape_title;
  var idx = opts.indexOf(cur);
  var next = opts[(idx + 1) % opts.length];
  _agentRec.soundscape_title = next;
  _tonightTrack = { title: next, source: 'swap', id: null, src: null };  // ← mark as swapped
  _applyAgentTrack();
  // Update mission in place
  var chooseStep = document.querySelector('.mission-step[data-key="choose"]');
  if (chooseStep) {
    var detail = chooseStep.querySelector('.mission-detail');
    if (detail) detail.textContent = next + ' — swapped by you';
  }
  var text = document.getElementById('agent-rec-text');
  if (text) text.textContent = 'Swapped to ' + next + ' — your call.';
  showToast('Swapped to ' + next, 'success');
}
```

Also update `_applyAgentTrack()` to set `_tonightTrack.source = 'agent'`:
```js
function _applyAgentTrack() {
  if (!_agentRec || !_agentRec.soundscape_title) return false;
  var chips = document.querySelectorAll('.track-chip');
  for (var i = 0; i < chips.length; i++) {
    if (chips[i].dataset.title === _agentRec.soundscape_title) {
      pickTrack(chips[i]);
      _tonightTrack = { title: _agentRec.soundscape_title, id: chips[i].dataset.id, src: chips[i].dataset.src, source: 'agent' };
      _updateTrackIndicator(_agentRec.soundscape_title);
      return true;
    }
  }
  _tonightTrack = { title: _agentRec.soundscape_title, source: 'agent' };
  _updateTrackIndicator(_agentRec.soundscape_title);
  return true;
}
```

---

### FIX-5: Implement `_refreshTrackList()`

**File:** `web/static/plan.js`

Add function near the top of the file:

```js
async function _refreshTrackList() {
  try {
    var tracks = await api('/api/music/library');
    var strip = document.getElementById('track-strip');
    if (!strip || !Array.isArray(tracks)) return;
    strip.innerHTML = '';
    tracks.forEach(function(t) {
      var moodTags = (t.mood_tags || []).join(',');
      var energy = t.energy_level || 'low';
      var owner = t.generated_by ? (t.generated_by === '{{ uid }}' ? 'mine' : 'public') : 'public';
      var vis = t.visibility || 'private';
      var btn = document.createElement('button');
      btn.className = 'track-chip px-3 py-2.5 bg-transparent border border-border rounded-xl cursor-pointer transition-all text-left hover:border-border-hover hover:bg-surface-hover group';
      btn.dataset.id = t.id || t.track_id;
      btn.dataset.src = t.src || '/media/music/' + (t.filename || '');
      btn.dataset.title = t.title || t.track_title || 'Untitled';
      btn.dataset.moodTags = moodTags;
      btn.dataset.energy = energy;
      btn.dataset.owner = owner;
      btn.dataset.visibility = vis;
      btn.innerHTML = t._chipHtml || ''; // Reuse existing chip HTML or generate inline
      strip.appendChild(btn);
    });
    // Re-sort by current mood if active
    if (_plan.mood) _sortTracksByMood(_plan.mood);
  } catch (e) { /* silently fail */ }
}
```

Alternatively (simpler approach): re-fetch and re-render chips by reusing the existing HTML structure. Since chips are rendered server-side in `_sound_lab.html`, a cleaner approach is to add a template-based render or to inline the chip generation in JS using the track data.

**Simpler alternative:** Replace chip rendering with a JS-driven approach. Have `_sound_lab.html` render a container with an ID, and `_refreshTrackList()` does a fetch + renders chips. The existing chips are rendered once by Jinja2; `_refreshTrackList()` does a full re-render from JS.

**Simpler simpler:** Just re-fetch from server and use existing chip-rendering logic. The simplest fix is to define `_refreshTrackList()` as:

```js
async function _refreshTrackList() {
  try {
    var tracks = await api('/api/music/library');
    if (!Array.isArray(tracks)) return;
    var strip = document.getElementById('track-strip');
    if (!strip) return;
    // Build a simple function to create a chip from a track object
    strip.innerHTML = tracks.map(function(t) {
      var src = t.src || '/media/music/' + (t.filename || '');
      var tags = (t.mood_tags || []).join(',');
      return '<button class="track-chip px-3 py-2.5 bg-transparent border border-border rounded-xl cursor-pointer transition-all text-left hover:border-border-hover hover:bg-surface-hover group" ' +
             'data-id="' + (t.id || t.track_id) + '" ' +
             'data-src="' + src + '" ' +
             'data-title="' + (t.title || t.track_title) + '" ' +
             'data-mood-tags="' + tags + '" ' +
             'data-energy="' + (t.energy_level || 'low') + '" ' +
             'data-owner="' + (t.generated_by === "' + '{{ uid }}'" ? 'mine' : 'public') + '" ' +
             'data-visibility="' + (t.visibility || 'private') + '">' +
             '<div class="flex items-center gap-1.5 mb-0.5">' +
             '<span class="energy-dot e-' + (t.energy_level || 'low') + '"></span>' +
             '<span class="text-[0.55rem] text-white/25 uppercase tracking-wider">' + (t.energy_level || 'low') + '</span>' +
             '</div>' +
             '<div class="text-xs font-medium text-white/70">' + (t.title || t.track_title) + '</div>' +
             '<div class="text-[0.55rem] text-white/25">' + (t.tags || '').split(',').join(', ') + '</div>' +
             '</button>';
    }).join('');
    if (_plan.mood) _sortTracksByMood(_plan.mood);
  } catch (e) {}
}
```

Note: the `{{ uid }}` Jinja template needs to be handled — pass `uid` as a JS variable from the template, or check `generated_by === user_id` server-side and include it in the API response.

---

### FIX-6: Add timeout to MCP verification

**File:** `web/static/plan.js`, function `_runMcpVerify`

```js
function _runMcpVerify(track, mood) {
  // …existing setup…
  var timer = setTimeout(function() {
    pending.textContent = 'Using deterministic data (MCP unavailable)';
    pending.classList.add('revealed');
    // Remove after 2s to keep the UI clean
    setTimeout(function() { pending.remove(); }, 2000);
  }, 12000);

  api('/api/agent/verify', 'POST', { track: track, mood: mood }).then(function(v) {
    clearTimeout(timer);
    if (!v || !v.mcp_used) { pending.remove(); return; }
    // …existing success handling…
  }).catch(function() {
    clearTimeout(timer);
    pending.remove();
  });
}
```

---

### FIX-7: Fix coach check-in priority and truncation

**File:** `agent/agent.py`, function `build_coach_checkin`

Reorder the priority:

```python
parts = []

# 1. Active experiment progress (most actionable)
if active:
    done = sum(1 for n in (active.get("nights") or []) if n.get("adhered"))
    target = active.get("target_nights", 3)
    parts.append(f"#{done}/{target} into the {active.get('label', 'experiment')} — stick with it tonight.")

# 2. Pending review
elif pending:
    title = (pending.get("plan") or {}).get("soundscape_title") or "last night"
    opener = "Morning — how did" if morning else "Before tonight, how did"
    parts.append(f"{opener} {title}? Rate to sharpen tonight's plan.")

# 3. Completed experiment result (only if not already shown in active)
elif completed and completed.get("result"):
    parts.append(completed["result"]["conclusion"].split(".")[0] + ".")  # First sentence only

# 4. Memory
elif memories:
    parts.append(f"Last time: {memories[0]['text'].lower()}.")

# 5. Fallback
if not parts:
    parts.append("Morning — let's see how you slept." if morning
                 else "Ready when you are — let's set you up for a good night.")
```

---

### FIX-8: Allow factor editing for "planned" sessions (optional, low priority)

**File:** `db/sessions.py`, function `update_session_factors`

Change the status check:
```python
if session.get("review") is None and session["status"] in ("planned", "active", "completed", "reviewed"):
    db.sleep_sessions.update_one(
        {"_id": oid},
        {"$set": {"review": {"factors": clean}, "updated_at": now}},
    )
```

This allows users to set factors on sessions that are still active (while playing).

---

## Execution Order

Do these in order:

1. **FIX-1** (skipReview → review API) — prevents data loss, low risk, high impact
2. **FIX-5** (implement _refreshTrackList) — enables tracks to appear after generation, needed for FIX-9
3. **FIX-2** (single-source-of-truth for tonight's track) — core state management fix
4. **FIX-3** (defer mood auto-selection) — ensures correct mood in recommendations
5. **FIX-4** (swapAgentTrack uses _tonightTrack) — ensures swap doesn't break state
6. **FIX-6** (MCP timeout) — prevents stuck UI
7. **FIX-7** (coach check-in priority) — cleaner UX, no data loss risk
8. **FIX-8** (factors on planned sessions) — optional, low risk

---

## Testing Checklist

After each fix:
- [ ] Fresh page load: mood defaults correctly, agent rec loads, track strip populated
- [ ] Change mood: chips reorder, _plan.track updates
- [ ] Manually pick track: _tonightTrack.source = 'manual', _plan.track.id set
- [ ] Use agent "Approve & start": track applied from agent rec, _tonightTrack.source = 'agent'
- [ ] "Swap track": cycles to next available track, indicator updates, _tonightTrack.source = 'swap'
- [ ] "Regenerate": fresh rec loads, chip list doesn't break
- [ ] "Start Sleep": correct track submitted (check network payload)
- [ ] Session plays → review banner appears
- [ ] Submit review: factors, rating, notes saved correctly
- [ ] Skip review: session status → "reviewed" (not deleted), experiment data preserved
- [ ] Experiment proposed → accepted → nights counted → result shown
- [ ] Coach check-in shows correct priority message
- [ ] Track generation: new track appears in strip, "Use tonight" works
- [ ] MCP verification: shows "Verifying…" then completes or times out gracefully
