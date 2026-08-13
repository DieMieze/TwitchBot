const PORT_COMPONENT_LABELS = {
    overlay: 'Overlay',
    webui: 'Config-UI',
    webhook: 'Webhook',
    pos_ui: 'Pos-UI',
    oauth: 'OAuth'
};

const OAUTH_COMPONENT = 'oauth';

let portsCache = null;

async function fetchPorts() {
    const response = await fetch('/api/ports');
    if (!response.ok) {
        throw new Error(`GET /api/ports failed: ${response.status}`);
    }
    const data = await response.json();
    portsCache = data;
    return data;
}

function renderPortsTable(data) {
    const table = document.getElementById('portsTable');
    if (!table) {
        return;
    }
    const rows = Object.keys(PORT_COMPONENT_LABELS).map(component => {
        const info = (data.ports || {})[component] || {};
        const port = info.port != null ? info.port : info.default;
        const free = info.free;
        const statusText = free ? 'frei' : 'belegt';
        const statusColor = free ? 'green' : 'red';
        return `
            <tr data-component="${component}">
                <td>${PORT_COMPONENT_LABELS[component]}</td>
                <td>${port}</td>
                <td>${info.default != null ? info.default : ''}</td>
                <td style="color:${statusColor}">${statusText}</td>
                <td><input type="number" min="1" max="65535" value="${port}" data-component="${component}" class="port-input"></td>
                <td><button onclick="savePort('${component}')" data-component="${component}">Speichern</button></td>
            </tr>
        `;
    });
    table.innerHTML = `
        <thead>
            <tr><th>Komponente</th><th>Port</th><th>Default</th><th>Status</th><th>Neuer Port</th><th></th></tr>
        </thead>
        <tbody>${rows.join('')}</tbody>
    `;
    const warningEl = document.getElementById('portsOauthWarning');
    if (warningEl) {
        warningEl.textContent = data.oauth_warning || '';
        warningEl.style.display = data.oauth_warning ? 'block' : 'none';
    }
    _renderOauthUri(data);
    const banner = document.getElementById('portsFirstRunBanner');
    if (banner) {
        const allDefault = Object.keys(PORT_COMPONENT_LABELS).every(component => {
            const info = (data.ports || {})[component] || {};
            return info.port == null || info.port === info.default;
        });
        banner.style.display = allDefault ? 'block' : 'none';
    }
}

function _oauthPortFromData(data) {
    if (data && data.oauth_redirect_uri) {
        const match = data.oauth_redirect_uri.match(/:(\d+)\/oauth\/callback$/);
        if (match) {
            return Number.parseInt(match[1], 10);
        }
    }
    const oauthInfo = ((data && data.ports) || {}).oauth || {};
    return oauthInfo.port != null ? oauthInfo.port : oauthInfo.default;
}

function _buildOauthRedirectUri(data) {
    if (data && data.oauth_redirect_uri) {
        return data.oauth_redirect_uri;
    }
    return 'http://localhost:' + _oauthPortFromData(data) + '/oauth/callback';
}

function _renderOauthUri(data) {
    const block = document.getElementById('portsOauthUriBlock');
    const codeEl = document.getElementById('portsOauthUri');
    if (!block || !codeEl) {
        return;
    }
    const uri = _buildOauthRedirectUri(data);
    codeEl.textContent = uri;
    block.style.display = 'block';
}

function copyOauthRedirectUri() {
    const codeEl = document.getElementById('portsOauthUri');
    if (!codeEl) {
        return;
    }
    const uri = codeEl.textContent || '';
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(uri).then(
            () => { alert('Redirect-URI kopiert: ' + uri); },
            () => { window.prompt('Redirect-URI:', uri); }
        );
    } else {
        window.prompt('Redirect-URI:', uri);
    }
}

async function loadPorts() {
    try {
        const data = await fetchPorts();
        renderPortsTable(data);
    } catch (err) {
        console.error(err);
        const table = document.getElementById('portsTable');
        if (table) {
            table.innerHTML = `<tr><td colspan="6">Fehler beim Laden der Ports: ${err.message}</td></tr>`;
        }
    }
}

function readPortInput(component) {
    const input = document.querySelector(`.port-input[data-component="${component}"]`);
    if (!input) {
        return null;
    }
    const raw = input.value.trim();
    if (raw === '') {
        return null;
    }
    const value = Number.parseInt(raw, 10);
    if (!Number.isInteger(value) || value < 1 || value > 65535) {
        return { error: `Port muss eine ganze Zahl zwischen 1 und 65535 sein (war: "${raw}").` };
    }
    return { value };
}

async function savePort(component) {
    const parsed = readPortInput(component);
    if (parsed && parsed.error) {
        alert(parsed.error);
        return;
    }
    if (!parsed) {
        alert('Kein Port eingegeben.');
        return;
    }
    const newPort = parsed.value;
    if (component === OAUTH_COMPONENT) {
        const confirmed = confirmOAuthChange(newPort);
        if (!confirmed) {
            return;
        }
    }
    try {
        const response = await fetch('/api/ports', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ component: component, port: newPort })
        });
        const data = await response.json();
        if (!response.ok) {
            alert(`Speichern fehlgeschlagen: ${data.error || response.status}`);
            return;
        }
        renderPortsTable(data);
        if (data.warning) {
            alert(data.warning);
        }
    } catch (err) {
        console.error(err);
        alert(`Speichern fehlgeschlagen: ${err.message}`);
    }
}

function confirmOAuthChange(newPort) {
    const uri = 'http://localhost:' + newPort + '/oauth/callback';
    return window.confirm(
        'Achtung: Du aenderst den OAuth-Port auf ' + newPort + '. ' +
        'Die Redirect URI in der Twitch Developer Console muss auf ' +
        uri + ' angepasst werden, ' +
        'sonst schlaegt die Autorisierung fehl. Fortfahren?'
    );
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        PORT_COMPONENT_LABELS,
        fetchPorts,
        renderPortsTable,
        loadPorts,
        readPortInput,
        savePort,
        confirmOAuthChange,
        copyOauthRedirectUri,
        _buildOauthRedirectUri,
        _renderOauthUri
    };
}
