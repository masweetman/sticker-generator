(function () {
  'use strict';

  var sheetId = window.SHEET_ID;
  var csrfToken = window.CSRF_TOKEN;
  var provider = window.PROVIDER || 'pollinations';
  var boundingPrompt = window.BOUNDING_PROMPT || '[INSERT SUBJECT HERE]';

  // ── Provider switcher ─────────────────────────────────────────────────────
  var providerSelect = document.getElementById('provider-select');
  if (providerSelect) {
    providerSelect.value = provider;
    providerSelect.addEventListener('change', function () {
      var chosen = providerSelect.value;
      fetch('/api/user/provider/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({ provider: chosen })
      })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          provider = data.provider;
        } else {
          alert('Could not save provider preference: ' + (data.error || 'Unknown error'));
          providerSelect.value = provider; // revert
        }
      })
      .catch(function () {
        providerSelect.value = provider; // revert on network error
      });
    });
  }

  // Copy-mode state
  var copyMode = false;
  var clipboard = null; // { row, col }

  // Currently active cell
  var activeCell = null;

  // ── DOM refs ──────────────────────────────────────────────────────────────
  var modal = document.getElementById('cellModal');
  var $modal = $(modal);
  var modalTitle = document.getElementById('modalTitle');

  var generatePanel = document.getElementById('generate-panel');
  var actionPanel = document.getElementById('action-panel');
  var pastePanel = document.getElementById('paste-panel');

  var promptInput = document.getElementById('promptInput');
  var promptInputPaste = document.getElementById('promptInputPaste');
  var btnGenerate = document.getElementById('btn-generate');
  var btnGeneratePaste = document.getElementById('btn-generate-paste');
  var generateSpinner = document.getElementById('generate-spinner');

  var btnRegenerate = document.getElementById('btn-regenerate');
  var btnCopySticker = document.getElementById('btn-copy-sticker');
  var btnCopyAll = document.getElementById('btn-copy-all');
  var btnDeleteSticker = document.getElementById('btn-delete-sticker');
  var btnPasteSticker = document.getElementById('btn-paste-sticker');

  var btnCopyMode = document.getElementById('btn-copy-mode');
  var copyModeLabel = document.getElementById('copy-mode-label');

  // ── Copy mode toggle ──────────────────────────────────────────────────────
  btnCopyMode.addEventListener('click', function () {
    copyMode = !copyMode;
    copyModeLabel.textContent = copyMode ? 'On' : 'Off';
    btnCopyMode.classList.toggle('active', copyMode);
    if (!copyMode) clearCopySource();
  });

  function clearCopySource() {
    clipboard = null;
    document.querySelectorAll('.sticker-cell.copy-source').forEach(function (el) {
      el.classList.remove('copy-source');
    });
  }

  // ── Cell click ────────────────────────────────────────────────────────────
  document.querySelectorAll('.sticker-cell').forEach(function (cell) {
    cell.addEventListener('click', function () {
      var row = parseInt(cell.dataset.row, 10);
      var col = parseInt(cell.dataset.col, 10);
      var hasSticker = cell.dataset.hasSticker === '1';

      activeCell = cell;

      if (copyMode && clipboard) {
        // In copy-mode with something on clipboard: show paste panel
        showModal('Paste or Generate — (' + row + ',' + col + ')');
        showPanel('paste');
        return;
      }

      if (copyMode && hasSticker) {
        // In copy-mode, picking a source
        clearCopySource();
        clipboard = { row: row, col: col };
        cell.classList.add('copy-source');
        return;
      }

      if (hasSticker) {
        showModal('Cell (' + row + ',' + col + ')');
        showPanel('action');
      } else {
        showModal('Generate Sticker — (' + row + ',' + col + ')');
        showPanel('generate');
        promptInput.value = '';
        promptInput.focus();
      }
    });
  });

  // ── Show helpers ──────────────────────────────────────────────────────────
  function showModal(title) {
    modalTitle.textContent = title;
    $modal.modal('show');
  }

  function showPanel(which) {
    generatePanel.style.display = which === 'generate' ? '' : 'none';
    actionPanel.style.display = which === 'action' ? '' : 'none';
    pastePanel.style.display = which === 'paste' ? '' : 'none';
  }

  // ── Generate ──────────────────────────────────────────────────────────────
  function doGenerate(promptText) {
    if (!promptText) { alert('Please enter a prompt.'); return; }
    var row = parseInt(activeCell.dataset.row, 10);
    var col = parseInt(activeCell.dataset.col, 10);

    setGenerating(true);

    if (provider === 'puter') {
      var fullPrompt = boundingPrompt.replace('[INSERT SUBJECT HERE]', promptText);
      puter.ai.txt2img(fullPrompt)
        .then(function (imgEl) {
          // imgEl.src is a data URL — send it to the server to persist
          return fetch('/api/upload-sticker/', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
              sheet_id: sheetId,
              row: row,
              col: col,
              prompt: promptText,
              image_data: imgEl.src
            })
          });
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          setGenerating(false);
          if (data.success) {
            setCell(activeCell, data.image_url);
            $modal.modal('hide');
          } else {
            alert('Error: ' + (data.error || 'Unknown error'));
          }
        })
        .catch(function (e) {
          setGenerating(false);
          alert('Error: ' + e);
        });
      return;
    }

    fetch('/api/generate/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
      },
      body: JSON.stringify({
        sheet_id: sheetId,
        row: row,
        col: col,
        prompt: promptText
      })
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      setGenerating(false);
      if (data.success) {
        setCell(activeCell, data.image_url);
        $modal.modal('hide');
      } else {
        alert('Error: ' + (data.error || 'Unknown error'));
      }
    })
    .catch(function (e) {
      setGenerating(false);
      alert('Network error: ' + e);
    });
  }

  btnGenerate.addEventListener('click', function () {
    doGenerate(promptInput.value.trim());
  });

  btnGeneratePaste.addEventListener('click', function () {
    doGenerate(promptInputPaste.value.trim());
  });

  promptInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      doGenerate(promptInput.value.trim());
    }
  });

  function setGenerating(on) {
    btnGenerate.disabled = on;
    btnGeneratePaste.disabled = on;
    generateSpinner.style.display = on ? '' : 'none';
    if (on) generateSpinner.classList.add('spinning');
    else generateSpinner.classList.remove('spinning');
  }

  // ── Regenerate ────────────────────────────────────────────────────────────
  btnRegenerate.addEventListener('click', function () {
    $modal.modal('hide');
    showModal('Regenerate — (' + activeCell.dataset.row + ',' + activeCell.dataset.col + ')');
    promptInput.value = '';
    showPanel('generate');
    $modal.modal('show');
  });

  // ── Delete ────────────────────────────────────────────────────────────────
  btnDeleteSticker.addEventListener('click', function () {
    if (!confirm('Delete this sticker?')) return;
    var row = parseInt(activeCell.dataset.row, 10);
    var col = parseInt(activeCell.dataset.col, 10);

    fetch('/api/sticker/' + sheetId + '/' + row + '/' + col + '/', {
      method: 'DELETE',
      headers: { 'X-CSRFToken': csrfToken }
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.success) {
        clearCell(activeCell);
        $modal.modal('hide');
      } else {
        alert('Error: ' + (data.error || 'Unknown'));
      }
    })
    .catch(function (e) { alert('Network error: ' + e); });
  });

  // ── Copy to all cells ────────────────────────────────────────────────────
  btnCopyAll.addEventListener('click', function () {
    if (!confirm('Copy this sticker to every cell on the sheet?')) return;
    var srcRow = parseInt(activeCell.dataset.row, 10);
    var srcCol = parseInt(activeCell.dataset.col, 10);

    fetch('/api/copy-all/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
      },
      body: JSON.stringify({ sheet_id: sheetId, row: srcRow, col: srcCol })
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.success) {
        data.updated.forEach(function (item) {
          var cell = document.querySelector(
            '.sticker-cell[data-row="' + item.row + '"][data-col="' + item.col + '"]'
          );
          if (cell) setCell(cell, item.image_url);
        });
        $modal.modal('hide');
      } else {
        alert('Error: ' + (data.error || 'Unknown'));
      }
    })
    .catch(function (e) { alert('Network error: ' + e); });
  });

  // ── Copy sticker (mark in clipboard) ─────────────────────────────────────
  btnCopySticker.addEventListener('click', function () {
    clipboard = {
      row: parseInt(activeCell.dataset.row, 10),
      col: parseInt(activeCell.dataset.col, 10)
    };
    clearCopySource();
    activeCell.classList.add('copy-source');
    copyMode = true;
    copyModeLabel.textContent = 'On';
    btnCopyMode.classList.add('active');
    $modal.modal('hide');
  });

  // ── Paste ─────────────────────────────────────────────────────────────────
  btnPasteSticker.addEventListener('click', function () {
    if (!clipboard) return;
    var dstRow = parseInt(activeCell.dataset.row, 10);
    var dstCol = parseInt(activeCell.dataset.col, 10);

    fetch('/api/copy/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
      },
      body: JSON.stringify({
        from_sheet_id: sheetId,
        from_row: clipboard.row,
        from_col: clipboard.col,
        to_sheet_id: sheetId,
        to_row: dstRow,
        to_col: dstCol
      })
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.success) {
        setCell(activeCell, data.image_url);
        $modal.modal('hide');
      } else {
        alert('Error: ' + (data.error || 'Unknown'));
      }
    })
    .catch(function (e) { alert('Network error: ' + e); });
  });

  // ── Cell DOM helpers ──────────────────────────────────────────────────────
  function setCell(cell, imageUrl) {
    var existing = cell.querySelector('.sticker-img');
    if (existing) {
      existing.src = imageUrl + '?t=' + Date.now();
    } else {
      var placeholder = cell.querySelector('.cell-placeholder');
      if (placeholder) placeholder.remove();
      var img = document.createElement('img');
      img.src = imageUrl + '?t=' + Date.now();
      img.className = 'sticker-img';
      img.alt = '';
      cell.insertBefore(img, cell.querySelector('.cell-overlay'));
    }
    cell.dataset.hasSticker = '1';
  }

  function clearCell(cell) {
    var img = cell.querySelector('.sticker-img');
    if (img) img.remove();
    if (!cell.querySelector('.cell-placeholder')) {
      var ph = document.createElement('div');
      ph.className = 'cell-placeholder';
      ph.innerHTML = '<span class="glyphicon glyphicon-plus-sign"></span>';
      cell.insertBefore(ph, cell.querySelector('.cell-overlay'));
    }
    delete cell.dataset.hasSticker;
    cell.classList.remove('copy-source');
  }

})();
