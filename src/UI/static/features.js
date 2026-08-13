const FEATURE_COMPONENTS = ['moderation', 'overlay', 'webui'];

const FEATURE_LABELS = {
    moderation: 'Moderation',
    overlay: 'Overlay',
    webui: 'WebUI',
};

const FEATURE_DESCRIPTIONS = {
    moderation: 'Aktiviert Moderation-Reactions (ban/timeout/delete_message/purge) bei Chat-/Moderations-Events.',
    overlay: 'Startet das Overlay-Backend (Flask-SocketIO auf runtime.overlay.port). Nur in production/test aktiv; in silent nie. Wirksam beim nächsten Bot-Start.',
    webui: 'Aktiviert das webui Feature (Status-/Settings-Events für die lokale UI).',
};

let featuresCache = null;

async function fetchFeatures() {
    const response = await fetch('/api/features');
    if (!response.ok) {
        throw new Error(`GET /api/features failed: ${response.status}`);
    }
    const data = await response.json();
    featuresCache = data;
    return data;
}

function renderFeaturesTable(features) {
    const table = document.getElementById('featuresTable');
    if (!table) {
        return;
    }
    table.innerHTML = '';
    FEATURE_COMPONENTS.forEach(component => {
        const block = (features || {})[component] || {};
        const enabled = !!block.enabled;
        const label = FEATURE_LABELS[component] || component;
        const description = FEATURE_DESCRIPTIONS[component] || '';

        const row = document.createElement('div');
        row.style.display = 'flex';
        row.style.alignItems = 'center';
        row.style.gap = '8px';
        row.style.padding = '6px 0';
        row.style.borderBottom = '1px solid #eee';

        const nameSpan = document.createElement('span');
        nameSpan.textContent = label;
        nameSpan.style.fontWeight = 'bold';
        nameSpan.style.minWidth = '100px';
        row.appendChild(nameSpan);

        const descSpan = document.createElement('span');
        descSpan.textContent = description;
        descSpan.style.flex = '1';
        descSpan.style.fontSize = '0.9em';
        row.appendChild(descSpan);

        const toggleButton = document.createElement('button');
        toggleButton.type = 'button';
        toggleButton.textContent = enabled ? 'An' : 'Aus';
        toggleButton.classList.add('toggle-button');
        toggleButton.classList.toggle('active', enabled);
        toggleButton.onclick = () => saveFeature(component, !enabled);
        row.appendChild(toggleButton);

        table.appendChild(row);
    });
}

async function loadFeatures() {
    try {
        const data = await fetchFeatures();
        renderFeaturesTable(data);
    } catch (err) {
        console.error(err);
        const table = document.getElementById('featuresTable');
        if (table) {
            table.innerHTML = `Fehler beim Laden der Features: ${err.message}`;
        }
    }
}

async function saveFeature(component, enabled) {
    try {
        const response = await fetch('/api/features', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ component: component, enabled: enabled }),
        });
        const data = await response.json();
        if (!response.ok) {
            alert(`Speichern fehlgeschlagen: ${data.error || response.status}`);
            return;
        }
        renderFeaturesTable(data.features || data);
    } catch (err) {
        console.error(err);
        alert(`Speichern fehlgeschlagen: ${err.message}`);
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        FEATURE_COMPONENTS,
        FEATURE_LABELS,
        FEATURE_DESCRIPTIONS,
        fetchFeatures,
        renderFeaturesTable,
        loadFeatures,
        saveFeature,
    };
}
