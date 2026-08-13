let addCommandContainer; // Globale Referenz für den "+"-Button-Container

let commandConfigSchema = null;
let commandSchema = null;

const defaultTriggerTypes = ['command', 'time', 'channel_point_reward', 'first_time_chatter', 'new_chatter', 'follow', 'sub', 'cheer', 'raid', 'compare', 'role'];
const defaultReactionTypes = ['chat_reply', 'overlay_text', 'overlay_gif', 'clip', 'counter', 'moderation', 'streampet'];
const defaultOverlayActions = ['StreamPet'];
const defaultReactionDataKeys = ['animation', 'username'];
const defaultRoles = ['Everyone', 'Subscriber', 'VIP', 'Mod', 'Broadcaster'];
const EVERYONE_ROLE = 'Everyone';
const CLICKABLE_ROLES = ['Subscriber', 'VIP', 'Mod', 'Broadcaster'];
const defaultCounterActions = ['increment', 'decrement', 'set', 'reset', 'create', 'delete', 'query'];
const defaultModerationActions = ['ban', 'timeout', 'delete_message', 'purge'];
const defaultCompareOps = ['==', '!=', '>', '>=', '<', '<=', 'in', 'contains', 'regex'];

const TRIGGER_KINDS = ['and', 'or', 'not', 'leaf'];
const REACTION_KINDS = ['seq', 'if', 'switch', 'reaction'];

let triggerHintsCache = null;
let triggerHintsLoading = null;

function _schemaCommands() {
    return commandConfigSchema?.properties?.commands?.items?.properties;
}

function getTriggerTypes() {
    const conditionSchema = _schemaCommands()?.when?.oneOf || _schemaCommands()?.when?.anyOf;
    if (Array.isArray(conditionSchema)) {
        for (const opt of conditionSchema) {
            const enumValues = opt?.properties?.condition?.properties?.type?.enum;
            if (Array.isArray(enumValues) && enumValues.length) return enumValues;
        }
    }
    return defaultTriggerTypes;
}

function getReactionTypes() {
    const reactionSchema = _schemaCommands()?.reactions?.oneOf || _schemaCommands()?.reactions?.anyOf;
    if (Array.isArray(reactionSchema)) {
        for (const opt of reactionSchema) {
            const enumValues = opt?.properties?.reaction?.properties?.type?.enum;
            if (Array.isArray(enumValues) && enumValues.length) return enumValues;
        }
    }
    return defaultReactionTypes;
}

function getCompareOps() {
    const conditionSchema = _schemaCommands()?.when;
    const oneOf = conditionSchema?.oneOf || conditionSchema?.anyOf;
    if (Array.isArray(oneOf)) {
        for (const opt of oneOf) {
            const ops = opt?.properties?.condition?.properties?.op?.enum;
            if (Array.isArray(ops) && ops.length) return ops;
        }
    }
    return defaultCompareOps;
}

function getOverlayActions() {
    return defaultOverlayActions;
}

function getReactionDataKeys() {
    return defaultReactionDataKeys;
}

function getCounterActions() {
    return defaultCounterActions;
}

function getModerationActions() {
    return defaultModerationActions;
}

const ROLE_DISPLAY_OVERRIDE = { vip: 'VIP' };

function _roleDisplay(role) {
    if (ROLE_DISPLAY_OVERRIDE[role]) {
        return ROLE_DISPLAY_OVERRIDE[role];
    }
    return role.charAt(0).toUpperCase() + role.slice(1);
}

function getRoles() {
    const rolesEnum = _schemaCommands()?.roles?.items?.enum;
    if (Array.isArray(rolesEnum) && rolesEnum.length) {
        return rolesEnum.map(_roleDisplay);
    }
    return defaultRoles;
}

function getTriggerFieldsForType(type) {
    const conditionSchema = _schemaCommands()?.when;
    const oneOf = conditionSchema?.oneOf || conditionSchema?.anyOf;
    let typeProps = null;
    if (Array.isArray(oneOf)) {
        for (const opt of oneOf) {
            const props = opt?.properties?.condition?.properties;
            if (props && props.type && Array.isArray(props.type.enum) && props.type.enum.includes(type)) {
                typeProps = props;
                break;
            }
        }
    }
    if (!typeProps) {
        if (type === 'command') return ['command'];
        if (type === 'time') return ['interval_minutes'];
        if (type === 'channel_point_reward') return ['reward_id'];
        if (type === 'new_chatter') return ['time'];
        if (type === 'first_time_chatter') return [];
        if (type === 'cheer') return ['min_bits'];
        if (type === 'raid') return ['min_viewers'];
        if (type === 'compare') return ['field', 'op', 'value'];
        if (type === 'role') return ['roles'];
        return [];
    }
    const fieldMap = {
        command: 'command',
        time: 'interval_minutes',
        channel_point_reward: 'reward_id',
        new_chatter: 'time',
        cheer: 'min_bits',
        raid: 'min_viewers',
    };
    const mapped = fieldMap[type] || null;
    if (mapped && typeProps[mapped]) {
        return [mapped];
    }
    if (type === 'compare') {
        return ['field', 'op', 'value'];
    }
    const fields = Object.keys(typeProps).filter(k => k !== 'type');
    return fields;
}

function loadTriggerHints(callback) {
    if (triggerHintsCache) {
        callback(triggerHintsCache);
        return;
    }
    if (triggerHintsLoading) {
        triggerHintsLoading.push(callback);
        return;
    }
    triggerHintsLoading = [callback];
    fetch('/api/trigger_hints')
        .then(function (resp) { return resp.json(); })
        .then(function (hints) {
            triggerHintsCache = hints || {};
            const queued = triggerHintsLoading || [];
            triggerHintsLoading = null;
            queued.forEach(function (cb) { cb(triggerHintsCache); });
        })
        .catch(function () {
            triggerHintsLoading = null;
        });
}

function renderTriggerHint(hints, type) {
    const hint = hints && hints[type];
    if (!hint) return null;
    const small = document.createElement('small');
    small.style.display = 'block';
    small.style.opacity = '0.7';
    small.style.fontSize = '0.85em';
    small.style.marginLeft = '5px';
    small.textContent = hint.hint || '';
    return small;
}

function schemaDescription(obj) {
    return obj && typeof obj === 'object' && typeof obj.description === 'string' ? obj.description : '';
}

function getRoleDescription() {
    return schemaDescription(_schemaCommands()?.roles);
}

function loadConfigSchemaFromMessage(message) {
    if (message && message.type === 'config_schema') {
        if (message.schema) commandConfigSchema = message.schema;
        if (message.command_schema) commandSchema = message.command_schema;
        if (message.config_schema) commandConfigSchema = message.config_schema;
    }
}

function _ensureWhen(command) {
    if (!command.when || typeof command.when !== 'object') {
        command.when = { kind: 'and', children: [] };
    }
    return command.when;
}

function _ensureReactions(command) {
    if (!command.reactions || typeof command.reactions !== 'object' || !command.reactions.kind) {
        command.reactions = { kind: 'seq', children: [] };
    }
    return command.reactions;
}

function _newLeafCondition(type) {
    if (type === 'time') return { type: 'time', interval_minutes: 0 };
    if (type === 'channel_point_reward') return { type: 'channel_point_reward', reward_id: '' };
    if (type === 'new_chatter') return { type: 'new_chatter', time: 0 };
    if (type === 'first_time_chatter') return { type: 'first_time_chatter' };
    if (type === 'cheer') return { type: 'cheer', min_bits: 0 };
    if (type === 'raid') return { type: 'raid', min_viewers: 0 };
    if (type === 'follow') return { type: 'follow' };
    if (type === 'sub') return { type: 'sub' };
    if (type === 'compare') return { type: 'compare', field: '', op: '==', value: '' };
    if (type === 'role') return { type: 'role', roles: [] };
    return { type: 'command', command: '' };
}

function _newTriggerNode(kind) {
    if (kind === 'not') return { kind: 'not', child: { kind: 'leaf', condition: _newLeafCondition('command') } };
    if (kind === 'leaf') return { kind: 'leaf', condition: _newLeafCondition('command') };
    if (kind === 'or') return { kind: 'or', children: [] };
    return { kind: 'and', children: [] };
}

function _newReactionNode(kind) {
    if (kind === 'if') {
        return {
            kind: 'if',
            when: { kind: 'and', children: [] },
            then: { kind: 'reaction', reaction: { type: 'chat_reply', message: '' } },
            else: { kind: 'reaction', reaction: { type: 'chat_reply', message: '' } },
        };
    }
    if (kind === 'switch') {
        return {
            kind: 'switch',
            on: '',
            cases: [{ equals: '', then: { kind: 'reaction', reaction: { type: 'chat_reply', message: '' } } }],
            default: { kind: 'reaction', reaction: { type: 'chat_reply', message: '' } },
        };
    }
    if (kind === 'reaction') {
        return { kind: 'reaction', reaction: buildReactionForType('chat_reply') };
    }
    return { kind: 'seq', children: [] };
}

function loadCommandEditor(data) {
    if (!data) {
        return;
    }

    const commandList = document.getElementById('commandList');
    commandList.innerHTML = '';

    const commands = data.commands;

    commands.forEach(command => addcommandToList(command));

    addCommandContainer = document.createElement('div');
    addCommandContainer.style.marginTop = '10px';
    const addcommandButton = document.createElement('button');
    addcommandButton.textContent = '+ New command';
    addcommandButton.onclick = () => createNewcommand();
    addCommandContainer.appendChild(addcommandButton);

    const addCounterButton = document.createElement('button');
    addCounterButton.textContent = '+ New counter';
    addCounterButton.style.marginLeft = '6px';
    addCounterButton.title = 'Erstellt einen Counter als Single-Construct (switch über {args[0]} mit rollen-gesperrten Sub-Befehlen).';
    addCounterButton.onclick = () => createNewCounter();
    addCommandContainer.appendChild(addCounterButton);

    commandList.appendChild(addCommandContainer);
}

function _reactionHasType(reactionsNode, type) {
    if (!reactionsNode || typeof reactionsNode !== 'object') return false;
    if (reactionsNode.kind === 'reaction') {
        return reactionsNode.reaction && reactionsNode.reaction.type === type;
    }
    if (reactionsNode.kind === 'seq' || reactionsNode.kind === 'if' || reactionsNode.kind === 'switch') {
        const children = reactionsNode.children || [];
        if (reactionsNode.kind === 'if') {
            return _reactionHasType(reactionsNode.then, type) || _reactionHasType(reactionsNode.else, type);
        }
        if (reactionsNode.kind === 'switch') {
            const cases = reactionsNode.cases || [];
            return (
                _reactionHasType(reactionsNode.default, type) ||
                cases.some(c => _reactionHasType(c.then, type))
            );
        }
        return children.some(child => _reactionHasType(child, type));
    }
    return false;
}

function addcommandToList(command) {
    const commandList = document.getElementById('commandList');

    const commandContainer = document.createElement('div');
    commandContainer.style.display = 'flex';
    commandContainer.style.alignItems = 'center';
    commandContainer.style.marginBottom = '5px';

    const button = document.createElement('button');
    button.textContent = command.name;
    button.style.flex = '1';
    button.onclick = () => editcommand(command);
    button.dataset.commandId = command.name;
    commandContainer.appendChild(button);

    const removeButton = document.createElement('button');
    removeButton.textContent = '-';
    removeButton.style.marginLeft = '10px';
    removeButton.onclick = () => {
        const index = jsonBuffer.commands.indexOf(command);
        if (index > -1) {
            jsonBuffer.commands.splice(index, 1);
        }
        commandContainer.remove();
    };
    commandContainer.appendChild(removeButton);

    if (addCommandContainer && commandList.contains(addCommandContainer)) {
        commandList.insertBefore(commandContainer, addCommandContainer);
    } else {
        commandList.appendChild(commandContainer);
    }
}

function renderWhen(node, container, label) {
    container.innerHTML = '';
    if (label) {
        const lab = document.createElement('label');
        lab.textContent = label;
        container.appendChild(lab);
    }
    if (!node || typeof node !== 'object' || !node.kind) {
        node = { kind: 'and', children: [] };
    }
    const kindSelect = document.createElement('select');
    TRIGGER_KINDS.forEach(kind => {
        const opt = document.createElement('option');
        opt.value = kind;
        opt.textContent = displayLabel('nodeKinds', kind, kind);
        if (node.kind === kind) opt.selected = true;
        kindSelect.appendChild(opt);
    });
    kindSelect.onchange = () => {
        const newKind = kindSelect.value;
        const newNode = _newTriggerNode(newKind);
        Object.keys(node).forEach(k => delete node[k]);
        Object.assign(node, newNode);
        renderWhen(node, container, label);
    };
    container.appendChild(kindSelect);

    const nodeDiv = document.createElement('div');
    nodeDiv.style.marginLeft = '15px';
    nodeDiv.style.borderLeft = '1px solid #ccc';
    nodeDiv.style.paddingLeft = '8px';
    container.appendChild(nodeDiv);

    if (node.kind === 'and' || node.kind === 'or' || node.kind === 'all' || node.kind === 'any') {
        const normalizedKind = (node.kind === 'all') ? 'and' : (node.kind === 'any' ? 'or' : node.kind);
        if (normalizedKind !== node.kind) node.kind = normalizedKind;
        if (!Array.isArray(node.children)) node.children = [];
        node.children.forEach((child, index) => {
            const childRow = document.createElement('div');
            childRow.style.marginBottom = '4px';
            nodeDiv.appendChild(childRow);
            renderWhen(child, childRow);

            const removeBtn = document.createElement('button');
            removeBtn.textContent = '-';
            removeBtn.style.marginLeft = '6px';
            removeBtn.onclick = () => {
                node.children.splice(index, 1);
                renderWhen(node, container, label);
            };
            childRow.appendChild(removeBtn);
        });

        const addBtn = document.createElement('button');
        addBtn.textContent = '+';
        addBtn.onclick = () => {
            node.children.push(_newTriggerNode('leaf'));
            renderWhen(node, container, label);
        };
        nodeDiv.appendChild(addBtn);
    } else if (node.kind === 'not') {
        if (!node.child) node.child = _newTriggerNode('leaf');
        const childRow = document.createElement('div');
        nodeDiv.appendChild(childRow);
        renderWhen(node.child, childRow);
    } else if (node.kind === 'leaf') {
        renderLeafCondition(node, nodeDiv);
    }
}

function renderLeafCondition(node, container) {
    container.innerHTML = '';
    const condition = node.condition || (node.condition = _newLeafCondition('command'));
    const triggerTypes = getTriggerTypes();

    const typeSelect = document.createElement('select');
    triggerTypes.forEach(type => {
        const opt = document.createElement('option');
        opt.value = type;
        opt.textContent = displayLabel('triggerTypes', type, type);
        if (condition.type === type) opt.selected = true;
        typeSelect.appendChild(opt);
    });
    typeSelect.onchange = () => {
        const newType = typeSelect.value;
        const newCondition = _newLeafCondition(newType);
        Object.keys(condition).forEach(k => delete condition[k]);
        Object.assign(condition, newCondition);
        renderLeafCondition(node, container);
    };
    container.appendChild(typeSelect);

    if (condition.type === 'compare') {
        const ops = getCompareOps();
        const fieldInput = document.createElement('input');
        fieldInput.value = condition.field || '';
        fieldInput.placeholder = 'field (z. B. {counter:x:value})';
        fieldInput.oninput = () => { condition.field = fieldInput.value; };
        container.appendChild(fieldInput);

        const opSelect = document.createElement('select');
        ops.forEach(op => {
            const opt = document.createElement('option');
            opt.value = op;
            opt.textContent = op;
            if (condition.op === op) opt.selected = true;
            opSelect.appendChild(opt);
        });
        opSelect.onchange = () => { condition.op = opSelect.value; };
        container.appendChild(opSelect);

        const valueInput = document.createElement('input');
        valueInput.value = condition.value != null ? String(condition.value) : '';
        valueInput.placeholder = 'value';
        valueInput.oninput = () => { condition.value = valueInput.value; };
        container.appendChild(valueInput);
    } else if (condition.type === 'role') {
        if (!Array.isArray(condition.roles)) condition.roles = [];
        const everyoneKey = EVERYONE_ROLE.toLowerCase();
        condition.roles = condition.roles.filter(r => r !== everyoneKey);
        const roles = getRoles();
        const rolesRow = document.createElement('div');
        rolesRow.style.display = 'flex';
        rolesRow.style.flexWrap = 'wrap';
        rolesRow.style.gap = '4px';
        rolesRow.style.marginTop = '4px';
        roles.forEach(role => {
            const roleButton = document.createElement('button');
            roleButton.textContent = role;
            roleButton.classList.add('toggle-button');
            const roleKey = role.toLowerCase();
            const isEveryone = roleKey === everyoneKey;
            const isActive = isEveryone
                ? condition.roles.length === 0
                : condition.roles.includes(roleKey);
            roleButton.classList.toggle('active', isActive);
            if (isEveryone) {
                roleButton.disabled = true;
                roleButton.title = 'Everyone = keine Rollen-Einschränkung; automatisch aktiv wenn nichts anderes gewählt';
                roleButton.style.cursor = 'not-allowed';
                roleButton.style.opacity = '0.6';
            } else {
                roleButton.onclick = () => {
                    const idx = condition.roles.indexOf(roleKey);
                    if (idx > -1) {
                        condition.roles.splice(idx, 1);
                    } else {
                        condition.roles.push(roleKey);
                    }
                    renderLeafCondition(node, container);
                };
            }
            rolesRow.appendChild(roleButton);
        });
        container.appendChild(rolesRow);
        const roleHint = _renderRoleLeafHint();
        if (roleHint) container.appendChild(roleHint);
    } else {
        const fields = getTriggerFieldsForType(condition.type);
        fields.forEach(field => {
            const input = document.createElement('input');
            input.value = condition[field] != null ? condition[field] : '';
            input.placeholder = field;
            input.oninput = () => {
                if (field === 'interval_minutes' || field === 'min_bits' || field === 'min_viewers' || field === 'time') {
                    condition[field] = parseFloat(input.value) || 0;
                } else {
                    condition[field] = input.value;
                }
            };
            container.appendChild(input);
        });

        const hintNode = renderTriggerHint(triggerHintsCache, condition.type);
        if (hintNode) container.appendChild(hintNode);

        const matchHint = _renderMatchHint(condition.type);
        if (matchHint) container.appendChild(matchHint);
    }
}

function _renderMatchHint(type) {
    const section = LABELS.hints[type] || (type === 'banme' ? LABELS.hints.banme : null);
    const matchText = section && section.match;
    if (!matchText) return null;
    const small = document.createElement('small');
    small.style.display = 'block';
    small.style.opacity = '0.7';
    small.style.fontSize = '0.85em';
    small.style.marginLeft = '5px';
    small.style.marginTop = '4px';
    small.textContent = matchText;
    return small;
}

function _renderCounterHint() {
    const text = LABELS.hints.counter;
    if (!text) return null;
    const small = document.createElement('small');
    small.style.display = 'block';
    small.style.opacity = '0.7';
    small.style.fontSize = '0.85em';
    small.style.marginTop = '4px';
    small.textContent = text;
    return small;
}

function _renderRoleLeafHint() {
    const text = LABELS.hints.role;
    if (!text) return null;
    const small = document.createElement('small');
    small.style.display = 'block';
    small.style.opacity = '0.7';
    small.style.fontSize = '0.85em';
    small.style.marginTop = '4px';
    small.textContent = text;
    return small;
}

function _renderPlaceholderPreview(message, textInput) {
    if (typeof message !== 'string' || !message) {
        return null;
    }
    let preview = message
        .replace(/\{username\}/g, 'Bob')
        .replace(/\{target\}/g, 'Alice')
        .replace(/\{args\[0\]\}/g, 'Alice')
        .replace(/\{args\[1\]\}/g, 'reason')
        .replace(/\{channel\}/g, '#streamer')
        .replace(/\{event_name\}/g, 'chat.message');
    const small = document.createElement('small');
    small.style.display = 'block';
    small.style.opacity = '0.7';
    small.style.fontSize = '0.85em';
    small.style.marginTop = '2px';
    small.dataset.previewRoot = '1';
    const update = () => {
        const current = textInput.value || '';
        small.textContent = 'Vorschau: ' + current
            .replace(/\{username\}/g, 'Bob')
            .replace(/\{target\}/g, 'Alice')
            .replace(/\{args\[0\]\}/g, 'Alice')
            .replace(/\{args\[1\]\}/g, 'reason')
            .replace(/\{channel\}/g, '#streamer')
            .replace(/\{event_name\}/g, 'chat.message');
    };
    update();
    textInput.addEventListener('input', update);
    return small;
}

function buildReactionForType(type) {
    switch (type) {
        case 'chat_reply':
            return { type: 'chat_reply', message: '' };
        case 'overlay_text':
            return { type: 'overlay_text', text: '' };
        case 'overlay_gif':
            return { type: 'overlay_gif', gif_id: '', text: '' };
        case 'clip':
            return { type: 'clip' };
        case 'counter':
            return { type: 'counter', action: 'increment', name: '' };
        case 'moderation':
            return { type: 'moderation', action: 'timeout', target: '' };
        case 'streampet':
            return { type: 'streampet', gif_id: '' };
        default:
            return { type: 'chat_reply', message: '' };
    }
}

function reactionFieldsForType(type) {
    switch (type) {
        case 'chat_reply':
            return ['message'];
        case 'overlay_text':
            return ['text'];
        case 'overlay_gif':
            return ['gif_id', 'text'];
        case 'clip':
            return [];
        case 'counter':
            return ['action', 'name', 'amount', 'value', 'category', 'category_dependent', 'subcounter_name'];
        case 'moderation':
            return ['action', 'target'];
        case 'streampet':
            return ['gif_id'];
        default:
            return ['message'];
    }
}

function renderReactions(node, container, label) {
    container.innerHTML = '';
    if (label) {
        const lab = document.createElement('label');
        lab.textContent = label;
        container.appendChild(lab);
    }
    if (!node || typeof node !== 'object' || !node.kind) {
        node = { kind: 'seq', children: [] };
    }
    const kindSelect = document.createElement('select');
    REACTION_KINDS.forEach(kind => {
        const opt = document.createElement('option');
        opt.value = kind;
        opt.textContent = displayLabel('nodeKinds', kind, kind);
        if (node.kind === kind) opt.selected = true;
        kindSelect.appendChild(opt);
    });
    kindSelect.onchange = () => {
        const newKind = kindSelect.value;
        const newNode = _newReactionNode(newKind);
        Object.keys(node).forEach(k => delete node[k]);
        Object.assign(node, newNode);
        renderReactions(node, container, label);
    };
    container.appendChild(kindSelect);

    const nodeDiv = document.createElement('div');
    nodeDiv.style.marginLeft = '15px';
    nodeDiv.style.borderLeft = '1px solid #ccc';
    nodeDiv.style.paddingLeft = '8px';
    container.appendChild(nodeDiv);

    if (node.kind === 'seq') {
        if (!Array.isArray(node.children)) node.children = [];
        node.children.forEach((child, index) => {
            const row = document.createElement('div');
            row.style.marginBottom = '4px';
            nodeDiv.appendChild(row);
            renderReactions(child, row);

            const removeBtn = document.createElement('button');
            removeBtn.textContent = '-';
            removeBtn.style.marginLeft = '6px';
            removeBtn.onclick = () => {
                node.children.splice(index, 1);
                renderReactions(node, container, label);
            };
            row.appendChild(removeBtn);
        });

        const addBtn = document.createElement('button');
        addBtn.textContent = '+';
        addBtn.onclick = () => {
            node.children.push(_newReactionNode('reaction'));
            renderReactions(node, container, label);
        };
        nodeDiv.appendChild(addBtn);
    } else if (node.kind === 'if') {
        const whenLabel = document.createElement('label');
        whenLabel.textContent = 'When:';
        nodeDiv.appendChild(whenLabel);
        const whenDiv = document.createElement('div');
        nodeDiv.appendChild(whenDiv);
        if (!node.when) node.when = { kind: 'and', children: [] };
        renderWhen(node.when, whenDiv);

        const thenLabel = document.createElement('label');
        thenLabel.textContent = 'Then:';
        nodeDiv.appendChild(thenLabel);
        const thenDiv = document.createElement('div');
        nodeDiv.appendChild(thenDiv);
        if (!node.then) node.then = _newReactionNode('reaction');
        renderReactions(node.then, thenDiv);

        const elseLabel = document.createElement('label');
        elseLabel.textContent = 'Else:';
        nodeDiv.appendChild(elseLabel);
        const elseDiv = document.createElement('div');
        nodeDiv.appendChild(elseDiv);
        if (!node.else) node.else = _newReactionNode('reaction');
        renderReactions(node.else, elseDiv);
    } else if (node.kind === 'switch') {
        const onLabel = document.createElement('label');
        onLabel.textContent = 'On:';
        nodeDiv.appendChild(onLabel);
        const onInput = document.createElement('input');
        onInput.value = node.on || '';
        onInput.placeholder = '{args[0]} oder {counter:x:value}';
        onInput.oninput = () => { node.on = onInput.value; };
        nodeDiv.appendChild(onInput);

        if (!Array.isArray(node.cases)) node.cases = [];
        node.cases.forEach((caseNode, index) => {
            const row = document.createElement('div');
            row.style.marginBottom = '4px';
            nodeDiv.appendChild(row);

            const equalsLabel = document.createElement('label');
            equalsLabel.textContent = 'equals:';
            row.appendChild(equalsLabel);
            const equalsInput = document.createElement('input');
            equalsInput.value = caseNode.equals != null ? String(caseNode.equals) : '';
            equalsInput.oninput = () => { caseNode.equals = equalsInput.value; };
            row.appendChild(equalsInput);

            const thenDiv = document.createElement('div');
            row.appendChild(thenDiv);
            if (!caseNode.then) caseNode.then = _newReactionNode('reaction');
            renderReactions(caseNode.then, thenDiv);

            const removeBtn = document.createElement('button');
            removeBtn.textContent = '-';
            removeBtn.onclick = () => {
                node.cases.splice(index, 1);
                renderReactions(node, container, label);
            };
            row.appendChild(removeBtn);
        });

        const addCaseBtn = document.createElement('button');
        addCaseBtn.textContent = '+ case';
        addCaseBtn.onclick = () => {
            node.cases.push({ equals: '', then: _newReactionNode('reaction') });
            renderReactions(node, container, label);
        };
        nodeDiv.appendChild(addCaseBtn);

        const defaultLabel = document.createElement('label');
        defaultLabel.textContent = 'Default:';
        nodeDiv.appendChild(defaultLabel);
        const defaultDiv = document.createElement('div');
        nodeDiv.appendChild(defaultDiv);
        if (!node.default) node.default = _newReactionNode('reaction');
        renderReactions(node.default, defaultDiv);
    } else if (node.kind === 'reaction') {
        renderReactionLeaf(node, nodeDiv);
    }
}

function renderReactionLeaf(node, container) {
    container.innerHTML = '';
    const reaction = node.reaction || (node.reaction = buildReactionForType('chat_reply'));
    const reactionTypes = getReactionTypes();
    const counterActions = getCounterActions();
    const moderationActions = getModerationActions();

    const typeLabel = document.createElement('label');
    typeLabel.textContent = 'Type:';
    container.appendChild(typeLabel);

    const typeSelect = document.createElement('select');
    reactionTypes.forEach(type => {
        const opt = document.createElement('option');
        opt.value = type;
        opt.textContent = displayLabel('reactionTypes', type, type);
        if (reaction.type === type) opt.selected = true;
        typeSelect.appendChild(opt);
    });
    typeSelect.onchange = () => {
        const newType = typeSelect.value;
        const allowed = reactionFieldsForType(newType);
        Object.keys(reaction).forEach(key => {
            if (key !== 'type' && allowed.indexOf(key) === -1) {
                delete reaction[key];
            }
        });
        reaction.type = newType;
        const defaults = buildReactionForType(newType);
        allowed.forEach(field => {
            if (!(field in reaction)) {
                reaction[field] = defaults[field];
            }
        });
        renderReactionLeaf(node, container);
    };
    container.appendChild(typeSelect);

    if (reaction.type === 'chat_reply') {
        const messageInput = document.createElement('input');
        messageInput.value = reaction.message || '';
        messageInput.placeholder = 'Chat-Nachricht';
        messageInput.oninput = () => { reaction.message = messageInput.value; };
        container.appendChild(messageInput);
        const preview = _renderPlaceholderPreview(reaction.message, messageInput);
        if (preview) container.appendChild(preview);
    } else if (reaction.type === 'overlay_text') {
        const textInput = document.createElement('input');
        textInput.value = reaction.text || '';
        textInput.placeholder = 'Overlay-Text';
        textInput.oninput = () => { reaction.text = textInput.value; };
        container.appendChild(textInput);
        const preview = _renderPlaceholderPreview(reaction.text, textInput);
        if (preview) container.appendChild(preview);
    } else if (reaction.type === 'overlay_gif') {
        const gifInput = document.createElement('input');
        gifInput.value = reaction.gif_id || '';
        gifInput.placeholder = 'gif_id';
        gifInput.oninput = () => { reaction.gif_id = gifInput.value; };
        container.appendChild(gifInput);

        const textInput = document.createElement('input');
        textInput.value = reaction.text || '';
        textInput.placeholder = 'Overlay-Text';
        textInput.oninput = () => { reaction.text = textInput.value; };
        container.appendChild(textInput);
        const preview = _renderPlaceholderPreview(reaction.text, textInput);
        if (preview) container.appendChild(preview);
    } else if (reaction.type === 'counter') {
        const actionSelect = document.createElement('select');
        counterActions.forEach(action => {
            const opt = document.createElement('option');
            opt.value = action;
            opt.textContent = action;
            if (reaction.action === action) opt.selected = true;
            actionSelect.appendChild(opt);
        });
        if (!reaction.action) {
            reaction.action = counterActions[0] || 'increment';
            actionSelect.value = reaction.action;
        }
        actionSelect.onchange = () => {
            reaction.action = actionSelect.value;
            renderReactionLeaf(node, container);
        };
        container.appendChild(actionSelect);

        const nameInput = document.createElement('input');
        nameInput.value = reaction.name || '';
        nameInput.placeholder = 'counter name';
        nameInput.oninput = () => { reaction.name = nameInput.value; };
        container.appendChild(nameInput);

        const act = reaction.action;
        const numericFields = { increment: 'amount', decrement: 'amount', set: 'value' };
        const numericField = numericFields[act];
        if (numericField) {
            const numInput = document.createElement('input');
            numInput.value = reaction[numericField] != null ? reaction[numericField] : (numericField === 'amount' ? '1' : '0');
            numInput.placeholder = numericField + (numericField === 'amount' ? ' (default 1)' : '');
            numInput.oninput = () => { reaction[numericField] = parseFloat(numInput.value) || 0; };
            container.appendChild(numInput);
        }

        const subFields = { add_subcounter: 1, select_subcounter: 1, delete_subcounter: 1 };
        if (subFields[act]) {
            const subInput = document.createElement('input');
            subInput.value = reaction.subcounter_name || '';
            subInput.placeholder = 'subcounter_name' + (act === 'select_subcounter' ? ' (leer = Auswahl aufheben)' : '');
            subInput.oninput = () => { reaction.subcounter_name = subInput.value; };
            container.appendChild(subInput);
        }

        const catWrap = document.createElement('div');
        catWrap.style.marginTop = '4px';
        const catToggleLabel = document.createElement('label');
        catToggleLabel.style.display = 'flex';
        catToggleLabel.style.alignItems = 'center';
        catToggleLabel.style.gap = '4px';
        const catCheckbox = document.createElement('input');
        catCheckbox.type = 'checkbox';
        catCheckbox.checked = !!reaction.category_dependent;
        catCheckbox.title = 'ON: Category = aktuelle Twitch-Stream-Kategorie (game_name, nur production). OFF: statisches category-Feld.';
        const catToggleText = document.createElement('span');
        catToggleText.textContent = 'category_dependent (Stream-Kategorie)';
        catToggleLabel.appendChild(catCheckbox);
        catToggleLabel.appendChild(catToggleText);
        catWrap.appendChild(catToggleLabel);

        const catInput = document.createElement('input');
        catInput.value = reaction.category || '';
        catInput.placeholder = 'category (optional, default "default")';
        catInput.disabled = !!reaction.category_dependent;
        catInput.style.opacity = reaction.category_dependent ? '0.5' : '1';
        catInput.oninput = () => { reaction.category = catInput.value; };
        catWrap.appendChild(catInput);

        catCheckbox.onchange = () => {
            reaction.category_dependent = catCheckbox.checked;
            catInput.disabled = !!reaction.category_dependent;
            catInput.style.opacity = reaction.category_dependent ? '0.5' : '1';
        };
        container.appendChild(catWrap);

        const counterHint = _renderCounterHint();
        if (counterHint) container.appendChild(counterHint);
    } else if (reaction.type === 'moderation') {
        const actionSelect = document.createElement('select');
        moderationActions.forEach(action => {
            const opt = document.createElement('option');
            opt.value = action;
            opt.textContent = action;
            if (reaction.action === action) opt.selected = true;
            actionSelect.appendChild(opt);
        });
        if (!reaction.action) {
            reaction.action = moderationActions[0] || 'timeout';
            actionSelect.value = reaction.action;
        }
        actionSelect.onchange = () => { reaction.action = actionSelect.value; };
        container.appendChild(actionSelect);

        const targetInput = document.createElement('input');
        targetInput.value = reaction.target || '';
        targetInput.placeholder = 'target user';
        targetInput.oninput = () => { reaction.target = targetInput.value; };
        container.appendChild(targetInput);
    } else if (reaction.type === 'streampet') {
        const gifInput = document.createElement('input');
        gifInput.value = reaction.gif_id || '';
        gifInput.placeholder = 'gif_id';
        gifInput.oninput = () => { reaction.gif_id = gifInput.value; };
        container.appendChild(gifInput);
    }
}

function renderRolesEditor(command, rolesDiv) {
    rolesDiv.innerHTML = '';
    if (!command.roles) command.roles = [];
    const everyoneKey = EVERYONE_ROLE.toLowerCase();
    command.roles = command.roles.filter(r => r !== everyoneKey);
    const roles = getRoles();
    roles.forEach(role => {
        const roleButton = document.createElement('button');
        roleButton.textContent = role;
        roleButton.classList.add('toggle-button');
        const roleKey = role.toLowerCase();
        const isEveryone = roleKey === everyoneKey;
        const isActive = isEveryone
            ? command.roles.length === 0
            : command.roles.includes(roleKey);
        roleButton.classList.toggle('active', isActive);
        if (isEveryone) {
            roleButton.disabled = true;
            roleButton.title = 'Everyone = keine Rollen-Einschränkung; automatisch aktiv wenn nichts anderes gewählt';
            roleButton.style.cursor = 'not-allowed';
            roleButton.style.opacity = '0.6';
        } else {
            roleButton.onclick = () => {
                toggleRole(command, role);
                renderRolesEditor(command, rolesDiv);
            };
        }
        rolesDiv.appendChild(roleButton);
    });
}

const ROLE_AWARE_TRIGGER_TYPES = new Set(['command', 'new_chatter', 'first_time_chatter']);

function _triggerConditionTypes(command) {
    const types = new Set();
    const when = command.when;
    _collectLeafTypes(when, types);
    return types;
}

function _collectLeafTypes(node, types) {
    if (!node || typeof node !== 'object') return;
    if (node.kind === 'leaf' && node.condition && typeof node.condition.type === 'string') {
        types.add(node.condition.type);
    } else if (node.kind === 'and' || node.kind === 'or' || node.kind === 'all' || node.kind === 'any') {
        (node.children || []).forEach(c => _collectLeafTypes(c, types));
    } else if (node.kind === 'not' && node.child) {
        _collectLeafTypes(node.child, types);
    }
}

function updateRolesHint(command, editor) {
    const label = editor.querySelector('.roles-label');
    if (!label) return;
    let hint = label.nextElementSibling;
    if (!hint || !hint.classList.contains('roles-hint')) {
        hint = null;
    }
    const types = _triggerConditionTypes(command);
    const nonRoleAware = Array.from(types).filter(t => !ROLE_AWARE_TRIGGER_TYPES.has(t));
    if (nonRoleAware.length === 0) {
        if (hint) hint.remove();
        return;
    }
    const typeList = nonRoleAware.join(', ');
    const text = `Rollen-Filter wirken nur bei chat-basierten Triggern (command/new_chatter). Bei ${typeList}-Events liefert Twitch keine Rollen — der Filter würde hier alle außer 'everyone' blockieren.`;
    if (!hint) {
        hint = document.createElement('small');
        hint.classList.add('roles-hint');
        hint.style.display = 'block';
        hint.style.opacity = '0.7';
        hint.style.fontSize = '0.85em';
        hint.style.marginTop = '2px';
        label.insertAdjacentElement('afterend', hint);
    }
    hint.textContent = text;
}

function editcommand(command) {
    const editor = document.getElementById('commandEditor');
    editor.innerHTML = '';

    const nameLabel = document.createElement('label');
    nameLabel.textContent = 'Name:';
    const nameInput = document.createElement('input');
    nameInput.value = command.name;
    nameInput.oninput = () => {
        const oldName = command.name;
        command.name = nameInput.value;

        const commandButton = document.querySelector(`[data-command-id="${oldName}"]`);
        if (commandButton) {
            commandButton.textContent = nameInput.value;
            commandButton.dataset.commandId = nameInput.value;
        }
    };
    editor.appendChild(nameLabel);
    editor.appendChild(nameInput);

    const triggersLabel = document.createElement('label');
    triggersLabel.textContent = 'When:';
    editor.appendChild(triggersLabel);

    _ensureWhen(command);
    const whenDiv = document.createElement('div');
    editor.appendChild(whenDiv);
    if (!triggerHintsCache) {
        loadTriggerHints(function () { renderWhen(command.when, whenDiv); });
    } else {
        renderWhen(command.when, whenDiv);
    }

    const rolesLabel = document.createElement('label');
    rolesLabel.textContent = 'Roles:';
    rolesLabel.classList.add('roles-label');
    rolesLabel.title = getRoleDescription();
    editor.appendChild(rolesLabel);

    const rolesDiv = document.createElement('div');
    renderRolesEditor(command, rolesDiv);
    editor.appendChild(rolesDiv);

    updateRolesHint(command, editor);

    if (_reactionHasType(command.reactions, 'counter')) {
        const counterRolesHint = document.createElement('small');
        counterRolesHint.classList.add('roles-hint');
        counterRolesHint.style.display = 'block';
        counterRolesHint.style.opacity = '0.7';
        counterRolesHint.style.fontSize = '0.85em';
        counterRolesHint.style.marginTop = '2px';
        counterRolesHint.textContent = 'Trigger-Rollen steuern den Zugang zum Befehl. Sub-Befehl-Rollen werden per role-Leaf im Reaktionsbaum (if.when) gesetzt — der Scaffolder verriegelt delsub/reset (Broadcaster) und set/add/select/clear (Mods).';
        editor.appendChild(counterRolesHint);
    }

    const reactionsLabel = document.createElement('label');
    reactionsLabel.textContent = 'Reactions:';
    editor.appendChild(reactionsLabel);

    _ensureReactions(command);
    const reactionsDiv = document.createElement('div');
    editor.appendChild(reactionsDiv);
    renderReactions(command.reactions, reactionsDiv);
}

function createNewcommand() {
    const newcommand = createMockCommand();

    jsonBuffer.commands.push(newcommand);
    addcommandToList(newcommand);
    editcommand(newcommand);
}

function createMockCommand(name = 'New command') {
    return {
        name,
        when: {
            kind: 'and',
            children: [
                { kind: 'leaf', condition: { type: 'command', command: '!new_command' } }
            ]
        },
        reactions: { kind: 'seq', children: [] },
        roles: []
    };
}

function addTrigger(command, type = 'command', value = '') {
    let condition;
    if (type === 'time') {
        condition = { type: 'time', interval_minutes: parseFloat(value) || 0 };
    } else if (type === 'channel_point_reward') {
        condition = { type: 'channel_point_reward', reward_id: value || `MOCK_reward_${Date.now()}` };
    } else if (type === 'new_chatter') {
        condition = { type: 'new_chatter', time: parseFloat(value) || 0 };
    } else if (type === 'first_time_chatter') {
        condition = { type: 'first_time_chatter' };
    } else if (type === 'cheer') {
        condition = { type: 'cheer', min_bits: parseInt(value, 10) || 0 };
    } else if (type === 'raid') {
        condition = { type: 'raid', min_viewers: parseInt(value, 10) || 0 };
    } else if (type === 'follow' || type === 'sub') {
        condition = { type: type };
    } else {
        condition = { type: 'command', command: value };
    }
    const when = _ensureWhen(command);
    if (!Array.isArray(when.children)) when.children = [];
    when.children.push({ kind: 'leaf', condition });
    return condition;
}

function removeTrigger(command, index) {
    const when = _ensureWhen(command);
    if (Array.isArray(when.children) && index >= 0 && index < when.children.length) {
        when.children.splice(index, 1);
    }
}

function addReaction(command, type = 'chat_reply') {
    const reaction = buildReactionForType(type);
    const reactions = _ensureReactions(command);
    if (reactions.kind !== 'seq') {
        reactions.kind = 'seq';
        reactions.children = [];
    }
    if (!Array.isArray(reactions.children)) reactions.children = [];
    reactions.children.push({ kind: 'reaction', reaction });
    return { type: type, ...reaction };
}

function removeReaction(command, index) {
    const reactions = _ensureReactions(command);
    if (reactions.kind === 'seq' && Array.isArray(reactions.children) && index >= 0 && index < reactions.children.length) {
        reactions.children.splice(index, 1);
    }
}

function toggleTriggerType(command) {
    const when = _ensureWhen(command);
    if (when.kind === 'and' || when.kind === 'all') {
        when.kind = 'or';
    } else {
        when.kind = 'and';
    }
    if (!Array.isArray(when.children)) when.children = [];
    return when.kind;
}

function toggleRole(command, role) {
    const everyoneKey = EVERYONE_ROLE.toLowerCase();
    if (!command.roles) command.roles = [];
    command.roles = command.roles.filter(r => r !== everyoneKey);
    const roleKey = role.toLowerCase();
    if (roleKey === everyoneKey) {
        return command.roles.length === 0;
    }
    const roleIndex = command.roles.indexOf(roleKey);
    if (roleIndex > -1) {
        command.roles.splice(roleIndex, 1);
        return false;
    }
    command.roles.push(roleKey);
    return true;
}

// --- Counter scaffolder (single-construct switch with role-locked cases) ---

function _counterReaction(name, action, extra) {
    const reaction = { type: 'counter', action: action, name: name, category: 'default', category_dependent: false };
    if (extra) Object.assign(reaction, extra);
    return reaction;
}

function _chatReply(message) {
    return { type: 'chat_reply', message: message };
}

function _counterCaseFree(equals, counterReaction, chatReplyMessage) {
    return {
        equals: equals,
        then: {
            kind: 'seq',
            children: [
                { kind: 'reaction', reaction: counterReaction },
                { kind: 'reaction', reaction: _chatReply(chatReplyMessage) },
            ],
        },
    };
}

function _counterCaseRole(equals, roles, counterReaction, thenMsg, elseMsg) {
    return {
        equals: equals,
        then: {
            kind: 'if',
            when: { kind: 'leaf', condition: { type: 'role', roles: roles } },
            then: {
                kind: 'seq',
                children: [
                    { kind: 'reaction', reaction: counterReaction },
                    { kind: 'reaction', reaction: _chatReply(thenMsg) },
                ],
            },
            else: { kind: 'reaction', reaction: _chatReply(elseMsg) },
        },
    };
}

function _buildCounterSwitch(name) {
    const modBroad = ['mod', 'broadcaster'];
    const broad = ['broadcaster'];
    const cases = [
        _counterCaseFree('+', _counterReaction(name, 'increment', { amount: '{args[1]}' }),
            '{counter:' + name + ':name} +{args[1]} \u2192 {counter:' + name + ':value}{counter:' + name + ':subcounter_label}'),
        _counterCaseFree('-', _counterReaction(name, 'decrement', { amount: '{args[1]}' }),
            '{counter:' + name + ':name} \u2212{args[1]} \u2192 {counter:' + name + ':value}{counter:' + name + ':subcounter_label}'),
        _counterCaseRole('set', modBroad, _counterReaction(name, 'set', { value: '{args[1]}' }),
            '{counter:' + name + ':name} = {counter:' + name + ':value}',
            'Nur Mods d\u00fcrfen das setzen.'),
        _counterCaseRole('reset', broad, _counterReaction(name, 'reset'),
            '{counter:' + name + ':name} zur\u00fcckgesetzt',
            'Nur der Broadcaster darf das zur\u00fccksetzen.'),
        _counterCaseRole('add', modBroad, _counterReaction(name, 'add_subcounter', { subcounter_name: '{args[1]}' }),
            'Subcounter {args[1]} hinzugef\u00fcgt',
            'Nur Mods d\u00fcrfen Subcounter anlegen.'),
        _counterCaseRole('select', modBroad, _counterReaction(name, 'select_subcounter', { subcounter_name: '{args[1]}' }),
            'Subcounter {args[1]} aktiv',
            'Nur Mods d\u00fcrfen Subcounter w\u00e4hlen.'),
        _counterCaseRole('clear', modBroad, _counterReaction(name, 'clear_active_subcounter'),
            'Subcounter-Auswahl aufgehoben',
            'Nur Mods d\u00fcrfen das aufheben.'),
        _counterCaseRole('delsub', broad, _counterReaction(name, 'delete_subcounter', { subcounter_name: '{args[1]}' }),
            'Subcounter {args[1]} gel\u00f6scht',
            'Nur der Broadcaster darf Subcounter l\u00f6schen.'),
    ];
    return {
        kind: 'switch',
        on: '{args[0]}',
        cases: cases,
        default: {
            kind: 'seq',
            children: [
                { kind: 'reaction', reaction: _counterReaction(name, 'query') },
                { kind: 'reaction', reaction: _chatReply('{counter:' + name + ':value}{counter:' + name + ':subcounter_label}') },
            ],
        },
    };
}

function createNewCounter() {
    const name = window.prompt('Counter-Name (Befehl wird !<name>):');
    if (!name || !name.trim()) return null;
    const trimmed = name.trim();
    const command = {
        name: trimmed,
        when: {
            kind: 'and',
            children: [
                { kind: 'leaf', condition: { type: 'command', command: '!' + trimmed } },
            ],
        },
        roles: [],
        reactions: _buildCounterSwitch(trimmed),
    };
    jsonBuffer.commands.push(command);
    addcommandToList(command);
    editcommand(command);
    return command;
}

function _counterReactionOf(command) {
    let found = null;
    function walk(node) {
        if (found) return;
        if (!node || typeof node !== 'object') return;
        if (node.kind === 'reaction' && node.reaction && node.reaction.type === 'counter') {
            found = node.reaction;
            return;
        }
        if (node.kind === 'seq' || node.kind === 'if' || node.kind === 'switch') {
            if (node.kind === 'if') {
                walk(node.then);
                walk(node.else);
                return;
            }
            if (node.kind === 'switch') {
                (node.cases || []).forEach(c => walk(c.then));
                walk(node.default);
                return;
            }
            (node.children || []).forEach(walk);
        }
    }
    walk(command && command.reactions);
    return found;
}

function renameCounter(command) {
    const reaction = _counterReactionOf(command);
    if (!reaction) return null;
    const newName = window.prompt('Neuer Counter-Name:', reaction.name);
    if (!newName || !newName.trim()) return null;
    const trimmed = newName.trim();
    reaction.name = trimmed;
    if (command.when && Array.isArray(command.when.children)) {
        command.when.children.forEach(leaf => {
            if (leaf && leaf.kind === 'leaf' && leaf.condition && leaf.condition.type === 'command') {
                leaf.condition.command = '!' + trimmed;
            }
        });
    }
    command.name = trimmed;
    return trimmed;
}

function deleteCounter(command) {
    const index = jsonBuffer.commands.indexOf(command);
    if (index > -1) {
        jsonBuffer.commands.splice(index, 1);
    }
    return index > -1;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        createMockCommand,
        addTrigger,
        removeTrigger,
        addReaction,
        removeReaction,
        toggleTriggerType,
        toggleRole,
        EVERYONE_ROLE,
        CLICKABLE_ROLES,
        defaultRoles,
        getRoles,
        _roleDisplay,
        ROLE_AWARE_TRIGGER_TYPES,
        _triggerConditionTypes,
        _reactionHasType,
        _collectLeafTypes,
        _newTriggerNode,
        _newReactionNode,
        _ensureWhen,
        _ensureReactions,
        TRIGGER_KINDS,
        REACTION_KINDS,
        defaultTriggerTypes,
        defaultReactionTypes,
        createNewCounter,
        renameCounter,
        deleteCounter,
        _counterReactionOf,
        _buildCounterSwitch,
        _counterCaseFree,
        _counterCaseRole,
        _counterReaction,
        _chatReply,
    };
}
