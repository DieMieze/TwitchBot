// =============================================================================
// Config-UI — Overlay/StreamPet section
// =============================================================================
// Owns Stream_Pet.json keys: idle, animations, speech_bubble_text,
// speech_bubble_toggle. The stream_pet_config block (position/font/...) is
// maintained by the Pos-UI; POST /api/streampet merges top-level keys only,
// so this section never touches stream_pet_config. GIF uploads go to
// StreamPet/ via POST /api/streampet/upload (path format "StreamPet/<name>").
// Vanilla JS (no framework, no build), mirroring ports.js conventions.
// =============================================================================

let streampetCache = { idle: '', animations: {}, speech_bubble_text: '', speech_bubble_toggle: false };
let streampetGifs = [];

function setStreampetGifs(gifs) {
    streampetGifs = Array.isArray(gifs) ? gifs : [];
}

function setStreamPetStatus(message, color) {
    const el = document.getElementById('streampetStatus');
    if (!el) return;
    el.textContent = message || '';
    el.style.color = color || '';
}

async function fetchStreamPetConfig() {
    const response = await fetch('/api/streampet');
    if (!response.ok) {
        throw new Error('GET /api/streampet failed: ' + response.status);
    }
    return response.json();
}

async function fetchStreamPetGifs() {
    const response = await fetch('/api/streampet/gifs');
    if (!response.ok) {
        throw new Error('GET /api/streampet/gifs failed: ' + response.status);
    }
    return response.json();
}

function populateIdleSelect(selected) {
    const select = document.getElementById('spIdle');
    if (!select) return;
    select.innerHTML = '';
    const emptyOption = document.createElement('option');
    emptyOption.value = '';
    emptyOption.textContent = '(kein Idle)';
    select.appendChild(emptyOption);
    let matched = false;
    streampetGifs.forEach(name => {
        const opt = document.createElement('option');
        opt.value = 'StreamPet/' + name;
        opt.textContent = name;
        if (selected === opt.value) {
            opt.selected = true;
            matched = true;
        }
        select.appendChild(opt);
    });
    if (!matched && selected) {
        // idle path references a GIF no longer present; show it anyway.
        const opt = document.createElement('option');
        opt.value = selected;
        opt.textContent = selected + ' (fehlt)';
        opt.selected = true;
        select.appendChild(opt);
    }
}

function renderAnimationsTable() {
    const tbody = document.querySelector('#spAnimationsTable tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    const animations = streampetCache.animations || {};
    Object.keys(animations).forEach(name => {
        tbody.appendChild(buildAnimationRow(name, animations[name]));
    });
}

function buildAnimationRow(name, gifPath) {
    const tr = document.createElement('tr');

    const nameTd = document.createElement('td');
    const nameInput = document.createElement('input');
    nameInput.type = 'text';
    nameInput.value = name;
    nameInput.dataset.role = 'anim-name';
    nameInput.dataset.originalName = name;
    nameTd.appendChild(nameInput);
    tr.appendChild(nameTd);

    const gifTd = document.createElement('td');
    const gifSelect = document.createElement('select');
    gifSelect.dataset.role = 'anim-gif';
    gifSelect.dataset.originalName = name;
    const emptyOpt = document.createElement('option');
    emptyOpt.value = '';
    emptyOpt.textContent = '(kein)';
    gifSelect.appendChild(emptyOpt);
    let matched = false;
    streampetGifs.forEach(gifName => {
        const opt = document.createElement('option');
        opt.value = 'StreamPet/' + gifName;
        opt.textContent = gifName;
        if (gifPath === opt.value) {
            opt.selected = true;
            matched = true;
        }
        gifSelect.appendChild(opt);
    });
    if (!matched && gifPath) {
        const opt = document.createElement('option');
        opt.value = gifPath;
        opt.textContent = gifPath + ' (fehlt)';
        opt.selected = true;
        gifSelect.appendChild(opt);
    }
    gifTd.appendChild(gifSelect);
    tr.appendChild(gifTd);

    const removeTd = document.createElement('td');
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.textContent = 'Löschen';
    removeBtn.onclick = () => { tr.remove(); };
    removeTd.appendChild(removeBtn);
    tr.appendChild(removeTd);

    return tr;
}

function addStreamPetAnimation() {
    const tbody = document.querySelector('#spAnimationsTable tbody');
    if (!tbody) return;
    let idx = 1;
    while (streampetCache.animations && ('animation' + idx in streampetCache.animations)) idx++;
    const name = 'animation' + idx;
    tbody.appendChild(buildAnimationRow(name, ''));
}

function collectAnimations() {
    const animations = {};
    const rows = document.querySelectorAll('#spAnimationsTable tbody tr');
    rows.forEach(row => {
        const nameInput = row.querySelector('[data-role="anim-name"]');
        const gifSelect = row.querySelector('[data-role="anim-gif"]');
        if (!nameInput || !gifSelect) return;
        const name = nameInput.value.trim();
        const gif = gifSelect.value;
        if (name) animations[name] = gif;
    });
    return animations;
}

function applyConfigToForm(cfg) {
    streampetCache = cfg || {};
    streampetCache.animations = streampetCache.animations || {};
    populateIdleSelect(streampetCache.idle || '');
    renderAnimationsTable();
    const bubbleText = document.getElementById('spBubbleText');
    if (bubbleText) bubbleText.value = streampetCache.speech_bubble_text || '';
    const bubbleToggle = document.getElementById('spBubbleToggle');
    if (bubbleToggle) bubbleToggle.checked = !!streampetCache.speech_bubble_toggle;
}

async function loadStreamPet() {
    setStreamPetStatus('Lade…', '');
    try {
        const [cfg, gifs] = await Promise.all([fetchStreamPetConfig(), fetchStreamPetGifs()]);
        streampetGifs = Array.isArray(gifs) ? gifs : [];
        applyConfigToForm(cfg);
        setStreamPetStatus('', '');
    } catch (err) {
        console.error(err);
        setStreamPetStatus('Fehler beim Laden: ' + err.message, 'red');
    }
}

async function saveStreamPet() {
    const idle = (document.getElementById('spIdle') || {}).value || '';
    const speech_bubble_text = (document.getElementById('spBubbleText') || {}).value || '';
    const speech_bubble_toggle = !!(document.getElementById('spBubbleToggle') || {}).checked;
    const animations = collectAnimations();
    // Only the 4 Config-UI-owned keys; stream_pet_config stays untouched
    // server-side via the merge (top-level update only).
    const payload = {
        idle: idle,
        animations: animations,
        speech_bubble_text: speech_bubble_text,
        speech_bubble_toggle: speech_bubble_toggle,
    };
    setStreamPetStatus('Speichere…', '');
    try {
        const response = await fetch('/api/streampet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
            setStreamPetStatus('Speichern fehlgeschlagen: ' + (data.error || response.status), 'red');
            return;
        }
        setStreamPetStatus('Gespeichert.', 'green');
        setTimeout(() => setStreamPetStatus('', ''), 2000);
    } catch (err) {
        console.error(err);
        setStreamPetStatus('Speichern fehlgeschlagen: ' + err.message, 'red');
    }
}

async function uploadStreamPetGif() {
    const fileInput = document.getElementById('spUploadFile');
    if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
        setStreamPetStatus('Bitte eine .gif-Datei auswählen.', 'red');
        return;
    }
    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith('.gif')) {
        setStreamPetStatus('Nur .gif-Dateien sind erlaubt.', 'red');
        return;
    }
    const formData = new FormData();
    formData.append('file', file);
    setStreamPetStatus('Lade hoch…', '');
    try {
        const response = await fetch('/api/streampet/upload', {
            method: 'POST',
            body: formData,
        });
        const data = await response.json();
        if (!response.ok) {
            setStreamPetStatus('Upload fehlgeschlagen: ' + (data.error || response.status), 'red');
            return;
        }
        setStreamPetStatus('Hochgeladen: ' + data.path, 'green');
        // Refresh GIF list + reload config so dropdowns reflect the new file.
        try {
            streampetGifs = await fetchStreamPetGifs();
            populateIdleSelect(streampetCache.idle || '');
            renderAnimationsTable();
        } catch (e) {
            console.error(e);
        }
        if (fileInput) fileInput.value = '';
        setTimeout(() => setStreamPetStatus('', ''), 3000);
    } catch (err) {
        console.error(err);
        setStreamPetStatus('Upload fehlgeschlagen: ' + err.message, 'red');
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        fetchStreamPetConfig,
        fetchStreamPetGifs,
        populateIdleSelect,
        renderAnimationsTable,
        buildAnimationRow,
        addStreamPetAnimation,
        collectAnimations,
        applyConfigToForm,
        loadStreamPet,
        saveStreamPet,
        uploadStreamPetGif,
        setStreampetGifs,
    };
}
