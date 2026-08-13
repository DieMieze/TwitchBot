require('@jest/globals');

const {
  populateIdleSelect,
  renderAnimationsTable,
  buildAnimationRow,
  collectAnimations,
  applyConfigToForm,
  saveStreamPet,
  uploadStreamPetGif,
  setStreampetGifs,
} = require('../streampet');

function setupDocument() {
  document.body.innerHTML = `
    <div id="streampetStatus"></div>
    <select id="spIdle"></select>
    <table id="spAnimationsTable">
      <thead><tr><th>Name</th><th>GIF</th><th></th></tr></thead>
      <tbody></tbody>
    </table>
    <input id="spBubbleText" type="text">
    <input id="spBubbleToggle" type="checkbox">
    <input id="spUploadFile" type="file">
  `;
}

function mockFetchResponse(data, ok = true) {
  return {
    ok: ok,
    status: ok ? 200 : 400,
    json: async () => data,
  };
}

describe('populateIdleSelect', () => {
  beforeEach(() => setupDocument());

  test('renders an empty option plus one option per gif', () => {
    setStreampetGifs(['a.gif', 'b.gif']);
    populateIdleSelect('StreamPet/b.gif');
    const select = document.getElementById('spIdle');
    const options = Array.from(select.options).map(o => o.value);
    expect(options).toEqual(['', 'StreamPet/a.gif', 'StreamPet/b.gif']);
    expect(select.value).toBe('StreamPet/b.gif');
  });

  test('shows missing idle path as "(fehlt)" when not in gif list', () => {
    setStreampetGifs(['a.gif']);
    populateIdleSelect('StreamPet/gone.gif');
    const select = document.getElementById('spIdle');
    const missing = Array.from(select.options).find(o => o.value === 'StreamPet/gone.gif');
    expect(missing).toBeDefined();
    expect(missing.textContent).toMatch(/fehlt/);
    expect(select.value).toBe('StreamPet/gone.gif');
  });
});

// streampetGifs is module-private; expose it via applyConfigToForm path by
// setting the cache then calling render. Instead, test renderAnimationsTable
// by seeding streampetCache through applyConfigToForm.
describe('applyConfigToForm + renderAnimationsTable', () => {
  beforeEach(() => setupDocument());

  test('renders one row per animation', () => {
    setStreampetGifs(['wave.gif', 'dance.gif']);
    const cfg = {
      idle: 'StreamPet/idle.gif',
      animations: { wave: 'StreamPet/wave.gif', dance: 'StreamPet/dance.gif' },
      speech_bubble_text: 'Hi',
      speech_bubble_toggle: true,
    };
    applyConfigToForm(cfg);
    const rows = document.querySelectorAll('#spAnimationsTable tbody tr');
    expect(rows.length).toBe(2);
    const bubbleText = document.getElementById('spBubbleText');
    expect(bubbleText.value).toBe('Hi');
    expect(document.getElementById('spBubbleToggle').checked).toBe(true);
  });

  test('missing animations key defaults to empty table', () => {
    setStreampetGifs([]);
    applyConfigToForm({ idle: '', animations: undefined });
    const rows = document.querySelectorAll('#spAnimationsTable tbody tr');
    expect(rows.length).toBe(0);
  });
});

describe('collectAnimations', () => {
  beforeEach(() => setupDocument());

  test('collects name -> gif path from rows', () => {
    setStreampetGifs(['wave.gif']);
    applyConfigToForm({ animations: { wave: 'StreamPet/wave.gif' } });
    const result = collectAnimations();
    expect(result).toEqual({ wave: 'StreamPet/wave.gif' });
  });

  test('skips empty names', () => {
    setStreampetGifs(['wave.gif']);
    applyConfigToForm({ animations: { wave: 'StreamPet/wave.gif' } });
    // Blank out the name input.
    const nameInput = document.querySelector('[data-role="anim-name"]');
    nameInput.value = '   ';
    const result = collectAnimations();
    expect(result).toEqual({});
  });
});

describe('buildAnimationRow', () => {
  beforeEach(() => setupDocument());

  test('marks missing gif path as (fehlt)', () => {
    setStreampetGifs(['a.gif']);
    const row = buildAnimationRow('wave', 'StreamPet/missing.gif');
    const select = row.querySelector('[data-role="anim-gif"]');
    const missing = Array.from(select.options).find(o => o.value === 'StreamPet/missing.gif');
    expect(missing).toBeDefined();
    expect(missing.textContent).toMatch(/fehlt/);
    expect(select.value).toBe('StreamPet/missing.gif');
  });
});

describe('saveStreamPet', () => {
  beforeEach(() => setupDocument());

  test('posts only the 4 Config-UI-owned keys', async () => {
    setStreampetGifs(['pet.gif', 'wave.gif']);
    applyConfigToForm({
      idle: 'StreamPet/pet.gif',
      animations: { wave: 'StreamPet/wave.gif' },
      speech_bubble_text: 'Hi {username}',
      speech_bubble_toggle: true,
    });
    global.fetch = jest.fn().mockResolvedValue(mockFetchResponse({ message: 'ok' }));

    await saveStreamPet();

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/streampet',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          idle: 'StreamPet/pet.gif',
          animations: { wave: 'StreamPet/wave.gif' },
          speech_bubble_text: 'Hi {username}',
          speech_bubble_toggle: true,
        }),
      })
    );
  });

  test('shows error on non-ok response', async () => {
    setStreampetGifs([]);
    applyConfigToForm({ idle: '', animations: {}, speech_bubble_text: '', speech_bubble_toggle: false });
    global.fetch = jest.fn().mockResolvedValue(mockFetchResponse({ error: 'boom' }, false));
    await saveStreamPet();
    const status = document.getElementById('streampetStatus');
    expect(status.textContent).toMatch(/Speichern fehlgeschlagen/);
    expect(status.style.color).toBe('red');
  });
});

describe('uploadStreamPetGif', () => {
  beforeEach(() => setupDocument());

  test('warns when no file selected', async () => {
    global.fetch = jest.fn();
    await uploadStreamPetGif();
    const status = document.getElementById('streampetStatus');
    expect(status.textContent).toMatch(/gif-Datei/);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('posts FormData and refreshes gif list on success', async () => {
    setStreampetGifs([]);
    applyConfigToForm({ idle: '', animations: {} });
    const fileInput = document.getElementById('spUploadFile');
    Object.defineProperty(fileInput, 'files', {
      value: [{ name: 'new.gif' }],
      configurable: true,
    });

    const responses = [
      mockFetchResponse({ filename: 'new.gif', path: 'StreamPet/new.gif' }),
      mockFetchResponse(['new.gif', 'old.gif']),
    ];
    global.fetch = jest.fn().mockResolvedValue(responses[0]).mockResolvedValueOnce(responses[0]).mockResolvedValueOnce(responses[1]);

    await uploadStreamPetGif();

    expect(global.fetch).toHaveBeenCalledWith('/api/streampet/upload', expect.objectContaining({ method: 'POST' }));
    // After upload, gif list refreshed and idle select repopulated.
    const idleSelect = document.getElementById('spIdle');
    const optionValues = Array.from(idleSelect.options).map(o => o.value);
    expect(optionValues).toContain('StreamPet/new.gif');
    expect(optionValues).toContain('StreamPet/old.gif');
  });

  test('rejects non-gif file before upload', async () => {
    const fileInput = document.getElementById('spUploadFile');
    Object.defineProperty(fileInput, 'files', {
      value: [{ name: 'notes.txt' }],
      configurable: true,
    });
    global.fetch = jest.fn();
    await uploadStreamPetGif();
    const status = document.getElementById('streampetStatus');
    expect(status.textContent).toMatch(/Nur .gif/);
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
