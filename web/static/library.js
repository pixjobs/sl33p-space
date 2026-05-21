// ───── Library Management (no reload) ─────

async function deleteTrack(id, title) {
  if (!confirm('Delete "' + title + '" permanently?')) return;
  var res = await api('/api/music/' + id, 'DELETE');
  if (res.error) { showToast(res.error, 'error'); return; }
  showToast('Track deleted', 'success');
  var row = document.querySelector('.track-row[data-id="' + id + '"]');
  if (row) {
    row.style.opacity = '0';
    row.style.transform = 'translateX(20px)';
    setTimeout(function() { row.remove(); }, 200);
  }
}

async function archiveTrack(id) {
  var res = await api('/api/music/' + id + '/archive', 'POST');
  if (res.error) { showToast(res.error, 'error'); return; }
  showToast('Track archived', 'info');
  var row = document.querySelector('.track-row[data-id="' + id + '"]');
  if (row) {
    row.style.opacity = '0';
    row.style.transform = 'translateX(20px)';
    setTimeout(function() { row.remove(); }, 200);
  }
}

async function unarchiveTrack(id) {
  var res = await api('/api/music/' + id + '/unarchive', 'POST');
  if (res.error) { showToast(res.error, 'error'); return; }
  showToast('Track restored', 'success');
  await _refreshTrackList();
}
