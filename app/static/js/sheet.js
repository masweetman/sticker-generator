(function () {
  'use strict';

  var sheetId = window.SHEET_ID;
  var csrfToken = window.CSRF_TOKEN;
  var provider = window.PROVIDER || 'pollinations';
  var boundingPrompt = window.BOUNDING_PROMPT || '[INSERT SUBJECT HERE]';

  // ── Inline sheet rename ───────────────────────────────────────────────────
  var sheetNameDisplay = document.getElementById('sheet-name-display');
  var sheetNameInput = document.getElementById('sheet-name-input');

  function showRenameInput() {
    sheetNameInput.value = sheetNameDisplay.textContent.trim();
    sheetNameDisplay.style.display = 'none';
    sheetNameInput.style.display = '';
    sheetNameInput.focus();
    sheetNameInput.select();
  }

  function commitRename() {
    var newName = sheetNameInput.value.trim();
    if (!newName) {
      cancelRename();
      return;
    }
    if (newName === sheetNameDisplay.textContent.trim()) {
      cancelRename();
      return;
    }
    fetch('/api/rename-sheet/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
      },
      body: JSON.stringify({ sheet_id: sheetId, name: newName })
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.success) {
        sheetNameDisplay.textContent = data.name;
        document.title = data.name;
      } else {
        alert('Could not rename: ' + (data.error || 'Unknown error'));
      }
      sheetNameInput.style.display = 'none';
      sheetNameDisplay.style.display = '';
    })
    .catch(function (e) {
      alert('Network error: ' + e);
      cancelRename();
    });
  }

  function cancelRename() {
    sheetNameInput.style.display = 'none';
    sheetNameDisplay.style.display = '';
  }

  if (sheetNameDisplay) {
    sheetNameDisplay.addEventListener('click', showRenameInput);
  }
  if (sheetNameInput) {
    sheetNameInput.addEventListener('blur', commitRename);
    sheetNameInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); commitRename(); }
      if (e.key === 'Escape') { cancelRename(); }
    });
  }

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
  var btnCopyToNewSheet = document.getElementById('btn-copy-to-new-sheet');
  var btnDeleteSticker = document.getElementById('btn-delete-sticker');
  var btnPasteSticker = document.getElementById('btn-paste-sticker');

  var btnMic = null;      // no longer in HTML
  var btnMicPaste = null; // no longer in HTML

  var btnCopyMode = document.getElementById('btn-copy-mode');
  var copyModeLabel = document.getElementById('copy-mode-label');

  var listeningOverlay = document.getElementById('listening-overlay');
  var listeningOverlayPaste = document.getElementById('listening-overlay-paste');
  var promptArea = document.getElementById('prompt-area');
  var promptAreaPaste = document.getElementById('prompt-area-paste');
  var btnStopListening = document.getElementById('btn-stop-listening');
  var btnStopListeningPaste = document.getElementById('btn-stop-listening-paste');

  // ── Speech recognition ────────────────────────────────────────────────────
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  var activeRecognition = null;
  var silenceTimer = null;

  function setListeningUI(overlay, area, on) {
    overlay.style.display = on ? '' : 'none';
    area.style.display = on ? 'none' : '';
  }

  function startListening(targetInput, overlay, area) {
    if (!SpeechRecognition) return;
    if (activeRecognition) { activeRecognition.stop(); return; }

    var recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.continuous = true;   // keep mic open until silence or stop
    recognition.interimResults = true;

    activeRecognition = recognition;
    setListeningUI(overlay, area, true);

    function resetSilenceTimer() {
      clearTimeout(silenceTimer);
      silenceTimer = setTimeout(function () {
        if (activeRecognition) activeRecognition.stop();
      }, 3000);
    }

    recognition.onstart = function () {
      resetSilenceTimer();
    };

    recognition.onspeechstart = function () {
      resetSilenceTimer();
    };

    recognition.onresult = function (e) {
      resetSilenceTimer();
      // Use the latest final result; fall back to interim
      var transcript = '';
      for (var i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) {
          transcript = e.results[i][0].transcript;
        }
      }
      if (transcript) targetInput.value = transcript;
    };

    recognition.onerror = function (e) {
      clearTimeout(silenceTimer);
      if (e.error !== 'aborted' && e.error !== 'no-speech') {
        alert('Microphone error: ' + e.error);
      }
    };

    recognition.onend = function () {
      clearTimeout(silenceTimer);
      activeRecognition = null;
      setListeningUI(overlay, area, false);
    };

    recognition.start();
  }

  function stopListening() {
    clearTimeout(silenceTimer);
    if (activeRecognition) activeRecognition.stop();
  }

  if (btnStopListening) {
    btnStopListening.addEventListener('click', stopListening);
  }
  if (btnStopListeningPaste) {
    btnStopListeningPaste.addEventListener('click', stopListening);
  }

  // Stop listening when the modal is closed
  $modal.on('hide.bs.modal', function () {
    stopListening();
  });

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
        // Auto-start listening for empty cells if browser supports it
        if (SpeechRecognition) {
          startListening(promptInput, listeningOverlay, promptArea);
        } else {
          promptInput.focus();
        }
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

  // ── Copy to new sheet ─────────────────────────────────────────────────────
  btnCopyToNewSheet.addEventListener('click', function () {
    var srcRow = parseInt(activeCell.dataset.row, 10);
    var srcCol = parseInt(activeCell.dataset.col, 10);

    fetch('/api/copy-to-new-sheet/', {
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
        window.location.href = data.sheet_url;
      } else {
        alert('Error: ' + (data.error || 'Unknown error'));
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
