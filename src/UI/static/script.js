let jsonBuffer = null; // Globaler Buffer für die JSON-Daten

function showSection(sectionId) {
    document.querySelectorAll('section').forEach(section => {
        section.classList.add('hidden');
    });
    document.getElementById(sectionId).classList.remove('hidden');
}

async function loadCommands() {
    const response = await fetch('/api/commands');
    const data = await response.json();
    const commandList = document.getElementById('commandList');
    commandList.innerHTML = '';
    data.commands.forEach(command => {
        const li = document.createElement('li');
        li.textContent = command.name;
        commandList.appendChild(li);
    });
}

async function loadInitialData() {
    const response = await fetch('/api/commands');
    jsonBuffer = await response.json();
    loadCommandEditor(jsonBuffer);
}

document.addEventListener('DOMContentLoaded', loadInitialData);

async function saveAndExit() {
    const response = await fetch('/api/exit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(jsonBuffer) // Speichere den gesamten Buffer
    });

    if (response.ok) {
        const result = await response.json();
        alert(result.message);
    } else {
        const error = await response.json();
        console.error('Error saving JSON:', error);
        alert('Failed to save JSON. Check the console for details.');
    }
}