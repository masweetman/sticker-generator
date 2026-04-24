(function () {
  'use strict';

  var csrfToken = window.CSRF_TOKEN || '';

  // ── "Add to Sheet" modal ──────────────────────────────────────────────────
  var modal = document.getElementById('addToSheetModal');
  var $modal = $(modal);
  var modalImageId = document.getElementById('modal-image-id');
  var sheetSelect = document.getElementById('sheet-select');
  var newSheetName = document.getElementById('new-sheet-name');
  var btnConfirm = document.getElementById('btn-confirm-add-sheet');
  var addSheetSpinner = document.getElementById('add-sheet-spinner');
  var existingArea = document.getElementById('existing-sheet-area');
  var newSheetArea = document.getElementById('new-sheet-area');
  var radioButtons = document.querySelectorAll('input[name="sheet-choice"]');

  // Toggle existing/new sheet input areas
  radioButtons.forEach(function (radio) {
    radio.addEventListener('change', function () {
      var isNew = radio.value === 'new';
      existingArea.style.display = isNew ? 'none' : '';
      newSheetArea.style.display = isNew ? '' : 'none';
    });
  });

  // Populate sheet dropdown when modal opens
  $modal.on('show.bs.modal', function () {
    sheetSelect.innerHTML = '<option value="">Loading…</option>';
    fetch('/api/sheets/', {
      headers: { 'X-CSRFToken': csrfToken }
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      sheetSelect.innerHTML = '';
      if (!data.sheets || data.sheets.length === 0) {
        sheetSelect.innerHTML = '<option value="">No sheets yet</option>';
        return;
      }
      data.sheets.forEach(function (s) {
        var opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.name + ' (' + s.rows + '×' + s.cols + ')';
        sheetSelect.appendChild(opt);
      });
    })
    .catch(function () {
      sheetSelect.innerHTML = '<option value="">Could not load sheets</option>';
    });
  });

  // Open modal when "Add to Sheet" is clicked
  document.querySelectorAll('.btn-add-sheet').forEach(function (btn) {
    btn.addEventListener('click', function () {
      modalImageId.value = btn.dataset.imageId;
      // Reset radio to "existing"
      radioButtons.forEach(function (r) { r.checked = r.value === 'existing'; });
      existingArea.style.display = '';
      newSheetArea.style.display = 'none';
      newSheetName.value = '';
      btnConfirm.disabled = false;
      if (addSheetSpinner) addSheetSpinner.style.display = 'none';
      $modal.modal('show');
    });
  });

  // Confirm: add to sheet
  if (btnConfirm) {
    btnConfirm.addEventListener('click', function () {
      var imageId = modalImageId.value;
      var choice = document.querySelector('input[name="sheet-choice"]:checked');
      var isNew = choice && choice.value === 'new';
      var body;

      if (isNew) {
        var name = newSheetName.value.trim();
        if (!name) { alert('Please enter a name for the new sheet.'); return; }
        body = { new_sheet: true, name: name };
      } else {
        var sheetId = sheetSelect.value;
        if (!sheetId) { alert('Please select a sheet.'); return; }
        body = { sheet_id: parseInt(sheetId, 10) };
      }

      btnConfirm.disabled = true;
      if (addSheetSpinner) addSheetSpinner.style.display = '';

      fetch('/api/library/' + imageId + '/add-to-sheet/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken
        },
        body: JSON.stringify(body)
      })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          window.location.href = data.sheet_url;
        } else {
          alert('Error: ' + (data.error || 'Unknown error'));
          btnConfirm.disabled = false;
          if (addSheetSpinner) addSheetSpinner.style.display = 'none';
        }
      })
      .catch(function (e) {
        alert('Network error: ' + e);
        btnConfirm.disabled = false;
        if (addSheetSpinner) addSheetSpinner.style.display = 'none';
      });
    });
  }

  // ── Tag editor ────────────────────────────────────────────────────────────

  // Toggle tag editor visibility
  document.querySelectorAll('.btn-edit-tags').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var imageId = btn.dataset.imageId;
      var editor = document.getElementById('tag-editor-' + imageId);
      if (editor) {
        editor.style.display = editor.style.display === 'none' ? '' : 'none';
      }
    });
  });

  // Add tag
  document.querySelectorAll('.btn-add-tag').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var imageId = btn.dataset.imageId;
      var input = document.querySelector('.tag-input[data-image-id="' + imageId + '"]');
      var tagText = input ? input.value.trim() : '';
      if (!tagText) return;

      fetch('/api/library/' + imageId + '/tags/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({ tag: tagText })
      })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          if (input) input.value = '';
          _addTagToDOM(imageId, data.tag);
        } else {
          alert(data.error || 'Could not add tag.');
        }
      })
      .catch(function (e) { alert('Network error: ' + e); });
    });
  });

  // Allow Enter key in tag input
  document.querySelectorAll('.tag-input').forEach(function (input) {
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        var btn = document.querySelector('.btn-add-tag[data-image-id="' + input.dataset.imageId + '"]');
        if (btn) btn.click();
      }
    });
  });

  // Remove tag (delegated — works for dynamically added tags too)
  document.addEventListener('click', function (e) {
    var target = e.target.closest ? e.target.closest('.btn-remove-tag') : null;
    if (!target) return;
    e.preventDefault();
    var imageId = target.dataset.imageId;
    var tagText = target.dataset.tag;

    fetch('/api/library/' + imageId + '/tags/' + encodeURIComponent(tagText) + '/', {
      method: 'DELETE',
      headers: { 'X-CSRFToken': csrfToken }
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.success) {
        var span = target.parentElement;
        if (span) span.remove();
        // Also remove the display label from card-tags
        var cardTags = document.getElementById('tags-' + imageId);
        if (cardTags) {
          cardTags.querySelectorAll('a').forEach(function (a) {
            if (a.textContent.trim() === tagText) a.remove();
          });
        }
      } else {
        alert(data.error || 'Could not remove tag.');
      }
    })
    .catch(function (e) { alert('Network error: ' + e); });
  });

  function _addTagToDOM(imageId, tagText) {
    // Add to editable-tags area
    var area = document.getElementById('editable-tags-' + imageId);
    if (area) {
      var span = document.createElement('span');
      span.className = 'label label-default';
      span.style.cssText = 'margin:1px; display:inline-block;';
      span.innerHTML = tagText +
        ' <a href="#" class="btn-remove-tag" data-image-id="' + imageId +
        '" data-tag="' + tagText + '" style="color:#fff; margin-left:3px;">&times;</a>';
      area.appendChild(span);
    }
    // Add to card-tags display area
    var cardTags = document.getElementById('tags-' + imageId);
    if (cardTags) {
      var a = document.createElement('a');
      a.className = 'label label-info';
      a.href = '#';
      a.textContent = tagText;
      a.style.margin = '1px';
      cardTags.appendChild(a);
    }
  }

  // ── Delete library image ──────────────────────────────────────────────────
  document.querySelectorAll('.btn-delete-library').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (!confirm('Remove this sticker from the library?')) return;
      var imageId = btn.dataset.imageId;

      fetch('/api/library/' + imageId + '/', {
        method: 'DELETE',
        headers: { 'X-CSRFToken': csrfToken }
      })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          var card = document.getElementById('library-card-' + imageId);
          if (card) card.remove();
        } else {
          alert('Error: ' + (data.error || 'Unknown error'));
        }
      })
      .catch(function (e) { alert('Network error: ' + e); });
    });
  });

})();
