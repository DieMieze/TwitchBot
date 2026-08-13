require('@jest/globals');

const {
  PORT_COMPONENT_LABELS,
  fetchPorts,
  renderPortsTable,
  readPortInput,
  savePort,
  confirmOAuthChange,
} = require('../ports');

function setupDocument() {
  document.body.innerHTML = `
    <table id="portsTable"></table>
    <div id="portsOauthWarning"></div>
    <div id="portsFirstRunBanner"></div>
    <div id="portsOauthUriBlock"></div>
    <code id="portsOauthUri"></code>
  `;
}

function mockFetchResponse(data, ok = true) {
  return {
    ok: ok,
    status: ok ? 200 : 400,
    json: async () => data,
  };
}

describe('PORT_COMPONENT_LABELS', () => {
  test('contains all 5 components', () => {
    expect(Object.keys(PORT_COMPONENT_LABELS).sort()).toEqual(
      ['oauth', 'overlay', 'pos_ui', 'webhook', 'webui']
    );
  });
});

describe('fetchPorts', () => {
  beforeEach(() => setupDocument());

  test('returns parsed JSON on success', async () => {
    const payload = { ports: { overlay: { port: 5000, default: 5000, free: true } }, oauth_warning: null };
    global.fetch = jest.fn().mockResolvedValue(mockFetchResponse(payload));
    const data = await fetchPorts();
    expect(data.ports.overlay.port).toBe(5000);
  });

  test('throws on non-ok response', async () => {
    global.fetch = jest.fn().mockResolvedValue(mockFetchResponse({ error: 'boom' }, false));
    await expect(fetchPorts()).rejects.toThrow(/GET \/api\/ports failed/);
  });
});

describe('renderPortsTable', () => {
  beforeEach(() => setupDocument());

  test('renders one row per component', () => {
    const data = {
      ports: {
        overlay: { port: 5000, default: 5000, free: true },
        webui: { port: 5001, default: 5001, free: true },
        webhook: { port: 5002, default: 5002, free: false },
        pos_ui: { port: 5003, default: 5003, free: true },
        oauth: { port: 5003, default: 5003, free: true },
      },
      oauth_warning: null,
    };
    renderPortsTable(data);
    const rows = document.querySelectorAll('#portsTable tbody tr');
    expect(rows.length).toBe(5);
  });

  test('shows status text and color per free flag', () => {
    const data = {
      ports: { overlay: { port: 5000, default: 5000, free: false } },
      oauth_warning: null,
    };
    renderPortsTable(data);
    const cell = document.querySelector('#portsTable tbody tr td:nth-child(4)');
    expect(cell.textContent).toBe('belegt');
    expect(cell.style.color).toBe('red');
  });

  test('displays oauth_warning when present', () => {
    const data = { ports: {}, oauth_warning: 'Achtung!' };
    renderPortsTable(data);
    const el = document.getElementById('portsOauthWarning');
    expect(el.textContent).toBe('Achtung!');
    expect(el.style.display).toBe('block');
  });

  test('hides first-run banner when at least one port deviates', () => {
    const data = {
      ports: {
        overlay: { port: 6000, default: 5000, free: true },
        webui: { port: 5001, default: 5001, free: true },
      },
      oauth_warning: null,
    };
    renderPortsTable(data);
    const banner = document.getElementById('portsFirstRunBanner');
    expect(banner.style.display).toBe('none');
  });

  test('shows first-run banner when all ports equal defaults', () => {
    const data = {
      ports: {
        overlay: { port: 5000, default: 5000, free: true },
        webui: { port: 5001, default: 5001, free: true },
      },
      oauth_warning: null,
    };
    renderPortsTable(data);
    const banner = document.getElementById('portsFirstRunBanner');
    expect(banner.style.display).toBe('block');
  });

  test('renders the OAuth redirect URI from backend field when present', () => {
    const data = {
      ports: { oauth: { port: 5010, default: 5003, free: true } },
      oauth_warning: 'warn',
      oauth_redirect_uri: 'http://localhost:5010/oauth/callback',
    };
    renderPortsTable(data);
    const block = document.getElementById('portsOauthUriBlock');
    const codeEl = document.getElementById('portsOauthUri');
    expect(block.style.display).toBe('block');
    expect(codeEl.textContent).toBe('http://localhost:5010/oauth/callback');
  });

  test('derives the OAuth redirect URI from the oauth port when field missing', () => {
    const data = {
      ports: { oauth: { port: 5020, default: 5003, free: true } },
      oauth_warning: null,
    };
    renderPortsTable(data);
    const codeEl = document.getElementById('portsOauthUri');
    expect(codeEl.textContent).toBe('http://localhost:5020/oauth/callback');
  });
});

describe('readPortInput', () => {
  beforeEach(() => setupDocument());

  test('returns parsed value for valid input', () => {
    renderPortsTable({ ports: { overlay: { port: 5000, default: 5000, free: true } }, oauth_warning: null });
    const input = document.querySelector('.port-input[data-component="overlay"]');
    input.value = '5050';
    const result = readPortInput('overlay');
    expect(result).toEqual({ value: 5050 });
  });

  test('returns error object for out-of-range port', () => {
    renderPortsTable({ ports: { overlay: { port: 5000, default: 5000, free: true } }, oauth_warning: null });
    const input = document.querySelector('.port-input[data-component="overlay"]');
    input.value = '70000';
    const result = readPortInput('overlay');
    expect(result.error).toMatch(/1 und 65535/);
  });

  test('non-numeric text is sanitized to empty by number input (returns null)', () => {
    renderPortsTable({ ports: { overlay: { port: 5000, default: 5000, free: true } }, oauth_warning: null });
    const input = document.querySelector('.port-input[data-component="overlay"]');
    input.value = 'abc';
    // type="number" inputs clear invalid text to '' in browsers/jsdom.
    expect(input.value).toBe('');
    expect(readPortInput('overlay')).toBeNull();
  });

  test('returns null for empty input', () => {
    renderPortsTable({ ports: { overlay: { port: 5000, default: 5000, free: true } }, oauth_warning: null });
    const input = document.querySelector('.port-input[data-component="overlay"]');
    input.value = '';
    expect(readPortInput('overlay')).toBeNull();
  });
});

describe('confirmOAuthChange', () => {
  test('delegates to window.confirm', () => {
    const spy = jest.spyOn(global.window, 'confirm').mockReturnValue(true);
    expect(confirmOAuthChange(5010)).toBe(true);
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });
});

describe('savePort', () => {
  beforeEach(() => setupDocument());

  test('alerts on invalid input without calling fetch', async () => {
    global.fetch = jest.fn();
    renderPortsTable({ ports: { overlay: { port: 5000, default: 5000, free: true } }, oauth_warning: null });
    const input = document.querySelector('.port-input[data-component="overlay"]');
    input.value = '0';
    const alertSpy = jest.spyOn(global, 'alert').mockImplementation(() => {});
    await savePort('overlay');
    expect(global.fetch).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  test('posts component + port and re-renders on success', async () => {
    const updated = { ports: { overlay: { port: 5050, default: 5000, free: true } }, warning: null };
    global.fetch = jest.fn().mockResolvedValue(mockFetchResponse(updated));
    renderPortsTable({ ports: { overlay: { port: 5000, default: 5000, free: true } }, oauth_warning: null });
    const input = document.querySelector('.port-input[data-component="overlay"]');
    input.value = '5050';
    await savePort('overlay');
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/ports',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ component: 'overlay', port: 5050 }),
      })
    );
  });

  test('requires confirmation for oauth changes', async () => {
    global.fetch = jest.fn().mockResolvedValue(mockFetchResponse({ ports: {}, warning: 'warn' }));
    const confirmSpy = jest.spyOn(global.window, 'confirm').mockReturnValue(false);
    renderPortsTable({ ports: { oauth: { port: 5003, default: 5003, free: true } }, oauth_warning: null });
    const input = document.querySelector('.port-input[data-component="oauth"]');
    input.value = '5010';
    await savePort('oauth');
    expect(confirmSpy).toHaveBeenCalled();
    expect(global.fetch).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  test('alerts on non-ok response', async () => {
    global.fetch = jest.fn().mockResolvedValue(mockFetchResponse({ error: 'bad' }, false));
    renderPortsTable({ ports: { overlay: { port: 5000, default: 5000, free: true } }, oauth_warning: null });
    const input = document.querySelector('.port-input[data-component="overlay"]');
    input.value = '5050';
    const alertSpy = jest.spyOn(global, 'alert').mockImplementation(() => {});
    await savePort('overlay');
    expect(alertSpy).toHaveBeenCalledWith(expect.stringMatching(/Speichern fehlgeschlagen/));
    alertSpy.mockRestore();
  });
});
