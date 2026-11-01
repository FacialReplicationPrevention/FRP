// FRP private review viewer. Bundled, same-origin only: no external resources, no storage APIs,
// no innerHTML. All text from the server is inserted with textContent, never parsed as markup.
(function () {
  'use strict';

  const itemsNav = document.getElementById('items');
  const main = document.getElementById('main');
  let session = null;
  let activePlayer = null;

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    for (const [name, value] of Object.entries(attrs || {})) {
      if (name === 'text') node.textContent = value;
      else if (name === 'className') node.className = value;
      else if (name.startsWith('on')) node.addEventListener(name.slice(2), value);
      else node.setAttribute(name, String(value));
    }
    for (const child of children || []) if (child) node.appendChild(child);
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  async function getJson(url) {
    const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store' });
    if (!response.ok) throw new Error('request failed');
    return response.json();
  }

  async function postRecord(payload) {
    const response = await fetch('api/records', {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const body = await response.json().catch(() => ({ problems: ['unreadable response'] }));
    if (!response.ok) throw new Error((body.problems || ['rejected']).join('; '));
    return body.record_id;
  }

  function frameUrl(key, index) {
    return 'media/' + encodeURIComponent(key) + '/frame/' + String(index);
  }

  function mediaImage(alt) {
    return el('img', { alt: alt, draggable: 'false' });
  }

  // Frame-accurate player over a frame sequence: play, pause, step, scrub and exact selection.
  function createPlayer(item, fps, onFrame) {
    const count = item.frame_count;
    const state = window.FRPPlayer.createFrameState(count, item.default_frame);
    let timer = null;
    const img = mediaImage('Generated output frame');
    const missing = el('div', { className: 'missing', text: 'Frame unavailable', hidden: '' });
    img.addEventListener('error', () => { missing.hidden = false; img.hidden = true; });
    img.addEventListener('load', () => { missing.hidden = true; img.hidden = false; });
    const viewport = el('div', { className: 'viewport zoom-1' }, [img, missing]);
    const label = el('span', { className: 'frame-label' });
    const slider = el('input', {
      type: 'range', min: 0, max: Math.max(0, count - 1), step: 1, 'aria-label': 'Scrub frames',
    });
    const playButton = el('button', { type: 'button', text: 'Play' });

    function render() {
      const frame = state.frame();
      img.src = frameUrl(item.key, frame);
      slider.value = String(frame);
      label.textContent = window.FRPPlayer.frameLabel(frame, count);
      label.className = 'frame-label' + (frame === 0 ? ' first' : '');
      if (onFrame) onFrame(frame);
    }
    function pause() {
      state.pause();
      if (timer !== null) { clearInterval(timer); timer = null; }
      playButton.textContent = 'Play';
    }
    function play() {
      if (timer !== null || !state.play()) return;
      render();
      playButton.textContent = 'Pause';
      timer = setInterval(() => {
        state.tick();
        render();
        if (!state.playing()) pause();
      }, 1000 / fps);
    }
    function move(update) { pause(); update(); render(); }
    playButton.addEventListener('click', () => (timer === null ? play() : pause()));
    slider.addEventListener('input', () => move(() => state.select(Number(slider.value))));
    const controls = el('div', { className: 'controls' }, [
      playButton,
      el('button', { type: 'button', text: '◀ Frame', onclick: () => move(() => state.step(-1)) }),
      el('button', { type: 'button', text: 'Frame ▶', onclick: () => move(() => state.step(1)) }),
      slider,
      label,
    ]);
    render();
    return {
      viewport: viewport,
      controls: controls,
      select: (index) => move(() => state.select(index)),
      current: () => state.frame(),
      stop: pause,
    };
  }

  function zoomControl(viewports) {
    const select = el('select', { 'aria-label': 'Zoom' }, [1, 2, 3, 4].map(
      (z) => el('option', { value: z, text: z + '×' })));
    select.addEventListener('change', () => {
      for (const viewport of viewports) viewport.className = 'viewport zoom-' + select.value;
    });
    return el('label', { text: 'Zoom (both panels) ' }, [select]);
  }

  function renderNav(onSelect) {
    clear(itemsNav);
    session.items.forEach((item, position) => {
      const badge = session.mode === 'identity_inspection'
        ? item.item_status.replace('_', ' ')
        : (item.media_available ? 'clip' : 'media unavailable');
      itemsNav.appendChild(el('button', {
        type: 'button', 'data-position': position, onclick: () => onSelect(position),
      }, [el('span', { text: item.label }), el('span', { className: 'badge', text: badge })]));
    });
  }

  function markCurrent(position) {
    for (const button of itemsNav.querySelectorAll('button')) {
      button.setAttribute('aria-current', String(Number(button.dataset.position) === position));
    }
  }

  function resultLine() {
    return el('p', { className: 'result', role: 'status' });
  }

  // Mode A ----------------------------------------------------------------------------------
  function renderIdentityItem(position) {
    const item = session.items[position];
    if (activePlayer) activePlayer.stop();
    activePlayer = null;
    markCurrent(position);
    clear(main);
    main.appendChild(el('h2', { text: item.label }));
    main.appendChild(el('p', {
      className: 'status' + (item.item_status === 'available' ? '' : ' absent'),
      text: item.status_note,
    }));

    const referenceImage = mediaImage('Reference image');
    const referenceMissing = el('div', { className: 'missing', text: 'Reference unavailable' });
    const referenceViewport = el('div', { className: 'viewport zoom-1' },
      [item.reference_available ? referenceImage : referenceMissing]);
    if (item.reference_available) {
      referenceImage.src = 'media/' + encodeURIComponent(item.key) + '/reference';
    }
    const referencePanel = el('section', { className: 'panel' },
      [el('h2', { text: 'Original reference' }), referenceViewport]);

    const outputPanel = el('section', { className: 'panel' }, [el('h2', { text: 'Generated output' })]);
    const viewports = [referenceViewport];
    let thumbButtons = [];
    if (item.item_status === 'available' && item.frame_count > 0) {
      activePlayer = createPlayer(item, session.playback_fps, (frame) => {
        for (const button of thumbButtons) {
          button.setAttribute('aria-pressed', String(Number(button.dataset.index) === frame));
        }
      });
      outputPanel.appendChild(activePlayer.viewport);
      outputPanel.appendChild(activePlayer.controls);
      viewports.push(activePlayer.viewport);
    } else {
      outputPanel.appendChild(el('div', { className: 'viewport' },
        [el('div', { className: 'missing', text: 'No output to display (' + item.item_status.replace('_', ' ') + ')' })]));
    }
    main.appendChild(zoomControl(viewports));
    main.appendChild(el('div', { className: 'panels' }, [referencePanel, outputPanel]));

    if (activePlayer && item.sampled_frames.length) {
      main.appendChild(el('h2', { text: 'Sampled frames (manifest frame indices)' }));
      thumbButtons = item.sampled_frames.map((frame) => {
        const thumb = mediaImage('');
        thumb.src = frameUrl(item.key, frame.index);
        return el('button', {
          type: 'button', 'data-index': frame.index, title: frame.label,
          'aria-pressed': String(frame.index === activePlayer.current()),
          onclick: () => activePlayer.select(frame.index),
        }, [thumb, el('span', { className: 'caption', text: frame.first_frame ? 'Frame 0 (first)' : 'Frame ' + frame.index })]);
      });
      main.appendChild(el('div', { className: 'thumbs' }, thumbButtons));
    }

    main.appendChild(measurementsSection(item));
    main.appendChild(identityForm(item));
  }

  function measurementsSection(item) {
    const section = el('section', {}, [el('h2', { text: 'Automated measurements' })]);
    const button = el('button', {
      type: 'button',
      text: 'Reveal automated measurements',
    });
    section.appendChild(el('p', {
      text: 'Hidden by default to limit anchoring: record your first impression before revealing. Revealing is recorded with your observation.',
    }));
    section.appendChild(button);
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        const data = await getJson('api/items/' + encodeURIComponent(item.key) + '/measurements');
        section.appendChild(el('p', { className: 'notice', text: data.notice + ' Calibration: ' + data.calibration_status + '.' }));
        if (!data.face_evaluator) {
          section.appendChild(el('p', { text: 'No automated face evaluation is available for this item (not evaluated).' }));
        } else {
          section.appendChild(el('p', {
            text: 'Evaluator: ' + data.face_evaluator.name + ' ' + data.face_evaluator.revision +
              (data.face_evaluator.simulated ? ' (SIMULATED fixture)' : ''),
          }));
        }
        const rows = data.frames.map((frame) => el('tr', {}, [
          el('td', { text: String(frame.index) + (frame.first_frame ? ' (first, separate)' : '') }),
          el('td', { text: frame.face_status }),
          el('td', {
            text: frame.similarity === null ? '— (no score)' : frame.similarity.toFixed(3) + ' (uncalibrated)',
          }),
        ]));
        section.appendChild(el('table', {}, [
          el('thead', {}, [el('tr', {}, [
            el('th', { text: 'Frame' }), el('th', { text: 'Detection status' }), el('th', { text: 'Similarity' }),
          ])]),
          el('tbody', {}, rows),
        ]));
      } catch (error) {
        section.appendChild(el('p', { text: 'Measurements unavailable.' }));
      }
    });
    return section;
  }

  function identityForm(item) {
    const available = item.item_status === 'available';
    const options = session.judgements.map((judgement) => el('label', {}, [
      el('input', Object.assign({ type: 'radio', name: 'judgement', value: judgement },
        !available && judgement !== 'not_assessable' ? { disabled: '' } : {})),
      document.createTextNode(' ' + judgement.replace('_', ' ') + ' '),
    ]));
    const frameOnly = el('input', Object.assign({ type: 'checkbox' }, available ? {} : { disabled: '' }));
    const notes = el('textarea', {
      maxlength: 2000,
      placeholder: 'Private notes (stored only in private records; avoid personal information)',
    });
    const result = resultLine();
    const form = el('form', {}, [
      el('fieldset', {}, [el('legend', { text: 'Your observation (human judgement, not a score)' }), ...options]),
      el('label', {}, [frameOnly, document.createTextNode(' Refers only to the displayed frame')]),
      notes,
      el('button', { type: 'submit', text: 'Save observation' }),
      result,
    ]);
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const chosen = form.querySelector('input[name="judgement"]:checked');
      if (!chosen) { result.textContent = 'Choose a judgement first.'; return; }
      try {
        const id = await postRecord({
          key: item.key,
          judgement: chosen.value,
          frame_index: frameOnly.checked && activePlayer ? activePlayer.current() : null,
          notes: notes.value || null,
        });
        result.textContent = 'Saved as a new immutable record (' + id.slice(0, 8) + '…). Submit again to add another observation.';
        notes.value = '';
      } catch (error) {
        result.textContent = 'Not saved: ' + error.message;
      }
    });
    return el('section', {}, [el('h2', { text: 'Record observation' }), form]);
  }

  // Mode B ----------------------------------------------------------------------------------
  function renderQualityItem(position) {
    const item = session.items[position];
    if (activePlayer) activePlayer.stop();
    activePlayer = null;
    markCurrent(position);
    clear(main);
    main.appendChild(el('h2', { text: item.label + ' (blinding code ' + item.key + ')' }));
    const panel = el('section', { className: 'panel' });
    if (item.media_available) {
      activePlayer = createPlayer(item, session.playback_fps, null);
      panel.appendChild(activePlayer.viewport);
      panel.appendChild(activePlayer.controls);
      main.appendChild(zoomControl([activePlayer.viewport]));
    } else {
      panel.appendChild(el('p', { className: 'status absent', text: 'Media unavailable: record this clip as unscorable.' }));
    }
    main.appendChild(panel);
    main.appendChild(qualityForm(item));
  }

  function qualityForm(item) {
    const rubric = session.rubric;
    const [low, high] = rubric.scale;
    const fieldsets = rubric.criteria.map((criterion) => {
      const radios = [];
      for (let value = low; value <= high; value += 1) {
        radios.push(el('label', {}, [
          el('input', { type: 'radio', name: criterion.id, value: value }),
          document.createTextNode(' ' + value + ' '),
        ]));
      }
      return el('fieldset', {}, [el('legend', { text: criterion.label }), ...radios]);
    });
    const unscorable = el('input', Object.assign({ type: 'checkbox' }, item.media_available ? {} : { checked: '' }));
    const reason = el('select', { 'aria-label': 'Unscorable reason' },
      rubric.unscorable_reasons.map((r) => el('option', { value: r, text: r.replace(/_/g, ' ') })));
    const notes = el('textarea', {
      maxlength: 2000,
      placeholder: 'Private notes (stored only in private records; avoid personal information)',
    });
    const result = resultLine();
    const form = el('form', {}, [
      el('p', { text: 'Rubric ' + rubric.version + ': 1 = worst, 5 = best. Rate video usefulness only.' }),
      ...fieldsets,
      el('label', {}, [unscorable, document.createTextNode(' Unscorable — reason: ')]), reason,
      notes,
      el('button', { type: 'submit', text: 'Save rating' }),
      result,
    ]);
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      let payload;
      if (unscorable.checked) {
        payload = { key: item.key, status: 'unscorable', scores: null, unscorable_reason: reason.value };
      } else {
        const scores = {};
        for (const criterion of rubric.criteria) {
          const chosen = form.querySelector('input[name="' + criterion.id + '"]:checked');
          if (!chosen) { result.textContent = 'Rate every criterion or mark the clip unscorable.'; return; }
          scores[criterion.id] = Number(chosen.value);
        }
        payload = { key: item.key, status: 'scored', scores: scores, unscorable_reason: null };
      }
      payload.notes = notes.value || null;
      try {
        const id = await postRecord(payload);
        result.textContent = 'Saved as a new immutable record (' + id.slice(0, 8) + '…).';
        notes.value = '';
      } catch (error) {
        result.textContent = 'Not saved: ' + error.message;
      }
    });
    return el('section', {}, [el('h2', { text: 'Blinded quality rating' }), form]);
  }

  // Media must not be dragged, saved through the context menu or printed (best effort only).
  document.addEventListener('contextmenu', (event) => {
    if (event.target instanceof HTMLImageElement) event.preventDefault();
  });
  document.addEventListener('dragstart', (event) => event.preventDefault());

  async function start() {
    try {
      session = await getJson('api/session');
    } catch (error) {
      clear(main);
      main.appendChild(el('p', { text: 'The review session could not be loaded.' }));
      return;
    }
    const banners = document.getElementById('banners');
    for (const text of session.banners) banners.appendChild(el('div', { className: 'banner', text: text }));
    document.getElementById('mode-label').textContent =
      session.mode_label + ' — reviewer ' + session.reviewer_role_code;
    const render = session.mode === 'identity_inspection' ? renderIdentityItem : renderQualityItem;
    renderNav(render);
    if (session.items.length) render(0);
    else { clear(main); main.appendChild(el('p', { text: 'No items in this session.' })); }
  }

  start();
}());
