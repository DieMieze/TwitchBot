require('@jest/globals');

const {
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
  createNewCounter,
  renameCounter,
  deleteCounter,
  _counterReactionOf,
  _buildCounterSwitch,
  _counterCaseFree,
  _counterCaseRole,
  _counterReaction,
  _chatReply,
} = require('../commands');

const { LABELS, displayLabel } = require('../labels');

global.displayLabel = displayLabel;
global.LABELS = LABELS;

function makeCommand(overrides = {}) {
  const cmd = createMockCommand(overrides.name || 'Test command');
  if (overrides.when) {
    cmd.when = JSON.parse(JSON.stringify(overrides.when));
  } else if (overrides.conditions) {
    cmd.when = {
      kind: 'and',
      children: overrides.conditions.map(c => ({ kind: 'leaf', condition: c })),
    };
  }
  if (overrides.reactions) {
    cmd.reactions = JSON.parse(JSON.stringify(overrides.reactions));
  } else if (overrides.reactionList) {
    cmd.reactions = {
      kind: 'seq',
      children: overrides.reactionList.map(r => ({ kind: 'reaction', reaction: r })),
    };
  }
  cmd.roles = overrides.roles ? [...overrides.roles] : [];
  return cmd;
}

describe('createMockCommand', () => {
  test('creates a command with default name and when/reactions roots', () => {
    const cmd = createMockCommand();
    expect(cmd.name).toBe('New command');
    expect(cmd.when.kind).toBe('and');
    expect(cmd.when.children).toHaveLength(1);
    expect(cmd.when.children[0].kind).toBe('leaf');
    expect(cmd.when.children[0].condition.type).toBe('command');
    expect(cmd.when.children[0].condition.command).toBe('!new_command');
    expect(cmd.reactions).toEqual({ kind: 'seq', children: [] });
    expect(cmd.roles).toEqual([]);
  });

  test('creates a command with custom name', () => {
    const cmd = createMockCommand('Wave Greet');
    expect(cmd.name).toBe('Wave Greet');
  });

  test('returns independent instances', () => {
    const a = createMockCommand();
    const b = createMockCommand();
    a.name = 'A';
    expect(b.name).toBe('New command');
  });
});

describe('addTrigger', () => {
  test('adds a command trigger leaf to the when tree', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    const cond = addTrigger(cmd, 'command', '!wave');
    expect(cond.type).toBe('command');
    expect(cond.command).toBe('!wave');
    expect(cmd.when.children).toHaveLength(1);
    expect(cmd.when.children[0].kind).toBe('leaf');
  });

  test('adds a time trigger with interval_minutes', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    const cond = addTrigger(cmd, 'time', '5');
    expect(cond.type).toBe('time');
    expect(cond.interval_minutes).toBe(5);
  });

  test('adds a time trigger with invalid value falls back to 0', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    const cond = addTrigger(cmd, 'time', 'abc');
    expect(cond.interval_minutes).toBe(0);
  });

  test('adds a channel_point_reward trigger with explicit reward_id', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    const cond = addTrigger(cmd, 'channel_point_reward', 'MOCK_reward_123');
    expect(cond.type).toBe('channel_point_reward');
    expect(cond.reward_id).toBe('MOCK_reward_123');
  });

  test('adds a channel_point_reward trigger with generated MOCK_ reward_id', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    const cond = addTrigger(cmd, 'channel_point_reward', '');
    expect(cond.reward_id).toMatch(/^MOCK_reward_/);
  });

  test('adds a new_chatter trigger with time window', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    const cond = addTrigger(cmd, 'new_chatter', '1800');
    expect(cond.type).toBe('new_chatter');
    expect(cond.time).toBe(1800);
  });

  test('adds a first_time_chatter trigger with no fields', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    const cond = addTrigger(cmd, 'first_time_chatter');
    expect(cond.type).toBe('first_time_chatter');
    expect(cond.message).toBeUndefined();
    expect(cond.time).toBeUndefined();
  });

  test('adds a follow trigger with no extra fields', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    const cond = addTrigger(cmd, 'follow');
    expect(cond.type).toBe('follow');
    expect(cond.command).toBeUndefined();
    expect(cond.min_bits).toBeUndefined();
  });

  test('adds a sub trigger with no extra fields', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    const cond = addTrigger(cmd, 'sub');
    expect(cond.type).toBe('sub');
  });

  test('adds a cheer trigger with min_bits', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    const cond = addTrigger(cmd, 'cheer', '100');
    expect(cond.type).toBe('cheer');
    expect(cond.min_bits).toBe(100);
  });

  test('adds a raid trigger with min_viewers', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    const cond = addTrigger(cmd, 'raid', '10');
    expect(cond.type).toBe('raid');
    expect(cond.min_viewers).toBe(10);
  });

  test('adds a cheer trigger with invalid value falls back to 0', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    const cond = addTrigger(cmd, 'cheer', 'abc');
    expect(cond.min_bits).toBe(0);
  });

  test('defaults to command type when no type given', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    const cond = addTrigger(cmd);
    expect(cond.type).toBe('command');
    expect(cond.command).toBe('');
  });

  test('appends to existing when children', () => {
    const cmd = makeCommand();
    addTrigger(cmd, 'time', '5');
    expect(cmd.when.children).toHaveLength(2);
    expect(cmd.when.children[1].condition.type).toBe('time');
  });
});

describe('removeTrigger', () => {
  test('removes a trigger leaf by index', () => {
    const cmd = makeCommand({
      conditions: [
        { type: 'command', command: '!a' },
        { type: 'time', interval_minutes: 5 },
      ],
    });
    removeTrigger(cmd, 0);
    expect(cmd.when.children).toHaveLength(1);
    expect(cmd.when.children[0].condition.type).toBe('time');
  });

  test('does nothing for out-of-range index', () => {
    const cmd = makeCommand();
    removeTrigger(cmd, 99);
    expect(cmd.when.children).toHaveLength(1);
  });

  test('does nothing for negative index', () => {
    const cmd = makeCommand();
    removeTrigger(cmd, -1);
    expect(cmd.when.children).toHaveLength(1);
  });
});

describe('addReaction', () => {
  test('adds a chat_reply reaction leaf to the seq root', () => {
    const cmd = makeCommand();
    const reaction = addReaction(cmd, 'chat_reply');
    expect(reaction.type).toBe('chat_reply');
    expect(reaction.message).toBe('');
    expect(cmd.reactions.kind).toBe('seq');
    expect(cmd.reactions.children).toHaveLength(1);
    expect(cmd.reactions.children[0].kind).toBe('reaction');
    expect(cmd.reactions.children[0].reaction.message).toBe('');
  });

  test('adds a clip reaction with no extra fields', () => {
    const cmd = makeCommand();
    const reaction = addReaction(cmd, 'clip');
    expect(reaction.type).toBe('clip');
    expect(reaction.action).toBeUndefined();
    expect(reaction.message).toBeUndefined();
    expect(reaction.gif_id).toBeUndefined();
  });

  test('adds an overlay_text reaction with empty text', () => {
    const cmd = makeCommand();
    const reaction = addReaction(cmd, 'overlay_text');
    expect(reaction.type).toBe('overlay_text');
    expect(reaction.text).toBe('');
    expect(reaction.message).toBeUndefined();
  });

  test('adds an overlay_gif reaction with gif_id and text', () => {
    const cmd = makeCommand();
    const reaction = addReaction(cmd, 'overlay_gif');
    expect(reaction.type).toBe('overlay_gif');
    expect(reaction.gif_id).toBe('');
    expect(reaction.text).toBe('');
    expect(reaction.message).toBeUndefined();
  });

  test('adds a counter reaction with increment action and name', () => {
    const cmd = makeCommand();
    const reaction = addReaction(cmd, 'counter');
    expect(reaction.type).toBe('counter');
    expect(reaction.action).toBe('increment');
    expect(reaction.name).toBe('');
  });

  test('adds a moderation reaction with timeout action and target', () => {
    const cmd = makeCommand();
    const reaction = addReaction(cmd, 'moderation');
    expect(reaction.type).toBe('moderation');
    expect(reaction.action).toBe('timeout');
    expect(reaction.target).toBe('');
  });

  test('adds a streampet reaction with gif_id', () => {
    const cmd = makeCommand();
    const reaction = addReaction(cmd, 'streampet');
    expect(reaction.type).toBe('streampet');
    expect(reaction.gif_id).toBe('');
    expect(reaction.action).toBeUndefined();
  });

  test('defaults to chat_reply type when no type given', () => {
    const cmd = makeCommand();
    const reaction = addReaction(cmd);
    expect(reaction.type).toBe('chat_reply');
    expect(reaction.message).toBe('');
  });

  test('wraps a non-seq reactions root into a seq before appending', () => {
    const cmd = makeCommand({ reactions: { kind: 'reaction', reaction: { type: 'clip' } } });
    const reaction = addReaction(cmd, 'chat_reply');
    expect(reaction.type).toBe('chat_reply');
    expect(cmd.reactions.kind).toBe('seq');
    expect(cmd.reactions.children).toHaveLength(1);
  });
});

describe('removeReaction', () => {
  test('removes a reaction leaf by index from the seq root', () => {
    const cmd = makeCommand({
      reactionList: [
        { type: 'overlay_gif', gif_id: '', text: '' },
        { type: 'chat_reply', message: 'hi' },
      ],
    });
    removeReaction(cmd, 0);
    expect(cmd.reactions.children).toHaveLength(1);
    expect(cmd.reactions.children[0].reaction.type).toBe('chat_reply');
  });

  test('does nothing for out-of-range index', () => {
    const cmd = makeCommand({ reactionList: [{ type: 'clip' }] });
    removeReaction(cmd, 5);
    expect(cmd.reactions.children).toHaveLength(1);
  });
});

describe('toggleTriggerType', () => {
  test('toggles from and to or', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    const next = toggleTriggerType(cmd);
    expect(next).toBe('or');
    expect(cmd.when.kind).toBe('or');
  });

  test('toggles from or to and', () => {
    const cmd = makeCommand({ when: { kind: 'or', children: [] } });
    const next = toggleTriggerType(cmd);
    expect(next).toBe('and');
    expect(cmd.when.kind).toBe('and');
  });

  test('round-trips back to original type', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    toggleTriggerType(cmd);
    const next = toggleTriggerType(cmd);
    expect(next).toBe('and');
  });
});

describe('toggleRole', () => {
  test('adds mod role when not present', () => {
    const cmd = makeCommand();
    const active = toggleRole(cmd, 'Mod');
    expect(active).toBe(true);
    expect(cmd.roles).toContain('mod');
  });

  test('removes mod role when present', () => {
    const cmd = makeCommand({ roles: ['mod'] });
    const active = toggleRole(cmd, 'Mod');
    expect(active).toBe(false);
    expect(cmd.roles).not.toContain('mod');
  });

  test('adds broadcaster role', () => {
    const cmd = makeCommand();
    toggleRole(cmd, 'Broadcaster');
    expect(cmd.roles).toContain('broadcaster');
  });

  test('normalizes role to lowercase', () => {
    const cmd = makeCommand();
    toggleRole(cmd, 'Mod');
    expect(cmd.roles.every((r) => r === r.toLowerCase())).toBe(true);
  });

  test('initializes roles array when undefined', () => {
    const cmd = makeCommand();
    cmd.roles = undefined;
    const active = toggleRole(cmd, 'Mod');
    expect(active).toBe(true);
    expect(cmd.roles).toContain('mod');
  });

  test('supports both mod and broadcaster simultaneously', () => {
    const cmd = makeCommand();
    toggleRole(cmd, 'Mod');
    toggleRole(cmd, 'Broadcaster');
    expect(cmd.roles).toEqual(expect.arrayContaining(['mod', 'broadcaster']));
    expect(cmd.roles).toHaveLength(2);
  });
});

describe('toggleRole everyone-invariant', () => {
  test('Everyone is read-only and reports active when roles is empty', () => {
    const cmd = makeCommand();
    const active = toggleRole(cmd, 'Everyone');
    expect(active).toBe(true);
    expect(cmd.roles).toEqual([]);
  });

  test('Everyone is read-only and reports inactive when a role is set', () => {
    const cmd = makeCommand({ roles: ['mod'] });
    const active = toggleRole(cmd, 'Everyone');
    expect(active).toBe(false);
    expect(cmd.roles).toEqual(['mod']);
  });

  test('toggling Subscriber adds subscriber and makes Everyone inactive', () => {
    const cmd = makeCommand();
    const active = toggleRole(cmd, 'Subscriber');
    expect(active).toBe(true);
    expect(cmd.roles).toContain('subscriber');
    expect(toggleRole(cmd, 'Everyone')).toBe(false);
  });

  test('toggling VIP stores lowercase vip', () => {
    const cmd = makeCommand();
    toggleRole(cmd, 'VIP');
    expect(cmd.roles).toContain('vip');
    expect(cmd.roles.every((r) => r === r.toLowerCase())).toBe(true);
  });

  test('legacy everyone entry is sanitized on first toggle', () => {
    const cmd = makeCommand({ roles: ['everyone', 'mod'] });
    toggleRole(cmd, 'Mod');
    expect(cmd.roles).not.toContain('everyone');
    expect(cmd.roles).toEqual([]);
  });

  test('legacy everyone-only entry is sanitized to empty', () => {
    const cmd = makeCommand({ roles: ['everyone'] });
    toggleRole(cmd, 'Subscriber');
    expect(cmd.roles).toEqual(['subscriber']);
  });

  test('removing the last role re-enables Everyone indicator', () => {
    const cmd = makeCommand({ roles: ['mod'] });
    toggleRole(cmd, 'Mod');
    expect(cmd.roles).toEqual([]);
    expect(toggleRole(cmd, 'Everyone')).toBe(true);
  });
});

describe('integration: full command lifecycle', () => {
  test('build a command with when tree and reactions root', () => {
    const cmd = makeCommand({ name: 'Wave', when: { kind: 'and', children: [] } });
    addTrigger(cmd, 'command', '!wave');
    addTrigger(cmd, 'channel_point_reward', 'MOCK_reward_abc');
    addReaction(cmd, 'overlay_gif');
    addReaction(cmd, 'chat_reply');
    toggleRole(cmd, 'Broadcaster');

    expect(cmd.name).toBe('Wave');
    expect(cmd.when.kind).toBe('and');
    expect(cmd.when.children).toHaveLength(2);
    expect(cmd.when.children[0].condition).toEqual({ type: 'command', command: '!wave' });
    expect(cmd.when.children[1].condition.reward_id).toBe('MOCK_reward_abc');
    expect(cmd.reactions.kind).toBe('seq');
    expect(cmd.reactions.children).toHaveLength(2);
    expect(cmd.reactions.children[0].reaction.gif_id).toBe('');
    expect(cmd.reactions.children[0].reaction.text).toBe('');
    expect(cmd.reactions.children[1].reaction.message).toBe('');
    expect(cmd.roles).toEqual(['broadcaster']);
  });
});

describe('role constants and helpers', () => {
  test('defaultRoles includes everyone, subscriber, vip, mod, broadcaster', () => {
    expect(defaultRoles).toEqual(['Everyone', 'Subscriber', 'VIP', 'Mod', 'Broadcaster']);
  });

  test('EVERYONE_ROLE is Everyone', () => {
    expect(EVERYONE_ROLE).toBe('Everyone');
  });

  test('CLICKABLE_ROLES excludes Everyone', () => {
    expect(CLICKABLE_ROLES).toEqual(['Subscriber', 'VIP', 'Mod', 'Broadcaster']);
    expect(CLICKABLE_ROLES).not.toContain('Everyone');
  });

  test('_roleDisplay overrides vip to VIP', () => {
    expect(_roleDisplay('vip')).toBe('VIP');
  });

  test('_roleDisplay capitalizes other roles', () => {
    expect(_roleDisplay('mod')).toBe('Mod');
    expect(_roleDisplay('broadcaster')).toBe('Broadcaster');
    expect(_roleDisplay('subscriber')).toBe('Subscriber');
    expect(_roleDisplay('everyone')).toBe('Everyone');
  });
});

describe('_triggerConditionTypes', () => {
  test('collects condition types from a when tree', () => {
    const cmd = makeCommand({
      conditions: [
        { type: 'command', command: '!a' },
        { type: 'follow' },
      ],
    });
    const types = _triggerConditionTypes(cmd);
    expect(Array.from(types).sort()).toEqual(['command', 'follow']);
  });

  test('handles empty when children', () => {
    const cmd = makeCommand({ when: { kind: 'and', children: [] } });
    expect(Array.from(_triggerConditionTypes(cmd))).toEqual([]);
  });

  test('collects types from nested and/or/not', () => {
    const cmd = makeCommand({
      when: {
        kind: 'or',
        children: [
          { kind: 'leaf', condition: { type: 'command', command: '!a' } },
          {
            kind: 'not',
            child: { kind: 'leaf', condition: { type: 'follow' } },
          },
        ],
      },
    });
    const types = _triggerConditionTypes(cmd);
    expect(Array.from(types).sort()).toEqual(['command', 'follow']);
  });

  test('ROLE_AWARE_TRIGGER_TYPES contains command, new_chatter and first_time_chatter', () => {
    expect(ROLE_AWARE_TRIGGER_TYPES.has('command')).toBe(true);
    expect(ROLE_AWARE_TRIGGER_TYPES.has('new_chatter')).toBe(true);
    expect(ROLE_AWARE_TRIGGER_TYPES.has('first_time_chatter')).toBe(true);
    expect(ROLE_AWARE_TRIGGER_TYPES.has('follow')).toBe(false);
    expect(ROLE_AWARE_TRIGGER_TYPES.has('raid')).toBe(false);
  });
});

describe('_reactionHasType', () => {
  test('detects counter in a flat seq', () => {
    const root = {
      kind: 'seq',
      children: [
        { kind: 'reaction', reaction: { type: 'counter', action: 'increment', name: 'x' } },
      ],
    };
    expect(_reactionHasType(root, 'counter')).toBe(true);
    expect(_reactionHasType(root, 'clip')).toBe(false);
  });

  test('detects counter nested in an if branch', () => {
    const root = {
      kind: 'if',
      when: { kind: 'leaf', condition: { type: 'follow' } },
      then: { kind: 'reaction', reaction: { type: 'counter', action: 'increment', name: 'x' } },
      else: { kind: 'reaction', reaction: { type: 'chat_reply', message: 'no' } },
    };
    expect(_reactionHasType(root, 'counter')).toBe(true);
  });

  test('returns false for empty seq', () => {
    expect(_reactionHasType({ kind: 'seq', children: [] }, 'counter')).toBe(false);
  });
});

describe('node builders', () => {
  test('TRIGGER_KINDS includes and, or, not, leaf', () => {
    expect(TRIGGER_KINDS).toEqual(['and', 'or', 'not', 'leaf']);
  });

  test('REACTION_KINDS includes seq, if, switch, reaction', () => {
    expect(REACTION_KINDS).toEqual(['seq', 'if', 'switch', 'reaction']);
  });

  test('_newTriggerNode builds a not with a child', () => {
    const node = _newTriggerNode('not');
    expect(node.kind).toBe('not');
    expect(node.child.kind).toBe('leaf');
  });

  test('_newReactionNode builds an if with when/then/else', () => {
    const node = _newReactionNode('if');
    expect(node.kind).toBe('if');
    expect(node.when.kind).toBe('and');
    expect(node.then.kind).toBe('reaction');
    expect(node.else.kind).toBe('reaction');
  });

  test('_newReactionNode builds a switch with one case and default', () => {
    const node = _newReactionNode('switch');
    expect(node.kind).toBe('switch');
    expect(node.cases).toHaveLength(1);
    expect(node.default.kind).toBe('reaction');
  });

  test('_ensureWhen initializes a missing when', () => {
    const cmd = { name: 'x' };
    const when = _ensureWhen(cmd);
    expect(when.kind).toBe('and');
    expect(cmd.when).toBe(when);
  });

  test('_ensureReactions initializes a missing reactions root', () => {
    const cmd = { name: 'x' };
    const reactions = _ensureReactions(cmd);
    expect(reactions.kind).toBe('seq');
    expect(cmd.reactions).toBe(reactions);
  });
});

describe('_collectLeafTypes', () => {
  test('handles null and non-object nodes gracefully', () => {
    const types = new Set();
    _collectLeafTypes(null, types);
    _collectLeafTypes(undefined, types);
    _collectLeafTypes('not-an-object', types);
    expect(Array.from(types)).toEqual([]);
  });
});

function _stubElement() {
  const el = {
    style: {},
    classList: { add: () => {}, toggle: () => {}, remove: () => {}, contains: () => false },
    dataset: {},
    appendChild: (child) => child,
    removeChild: () => {},
    insertBefore: (child) => child,
    contains: () => false,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: () => {},
    removeEventListener: () => {},
    append: () => {},
    insertAdjacentElement: () => null,
    setAttribute: () => {},
    getAttribute: () => null,
    removeAttribute: () => {},
    focus: () => {},
    click: () => {},
  };
  return el;
}

describe('counter scaffolder helpers', () => {
  test('_counterReaction builds the default counter reaction', () => {
    const r = _counterReaction('deaths', 'increment', { amount: '{args[1]}' });
    expect(r.type).toBe('counter');
    expect(r.action).toBe('increment');
    expect(r.name).toBe('deaths');
    expect(r.category).toBe('default');
    expect(r.category_dependent).toBe(false);
    expect(r.amount).toBe('{args[1]}');
  });

  test('_chatReply builds a chat_reply reaction', () => {
    expect(_chatReply('hi')).toEqual({ type: 'chat_reply', message: 'hi' });
  });

  test('_counterCaseFree wraps a free case as seq(counter, chat_reply)', () => {
    const c = _counterCaseFree('+', { type: 'counter', action: 'increment', name: 'x' }, 'msg');
    expect(c.equals).toBe('+');
    expect(c.then.kind).toBe('seq');
    expect(c.then.children).toHaveLength(2);
    expect(c.then.children[0].kind).toBe('reaction');
    expect(c.then.children[0].reaction.type).toBe('counter');
    expect(c.then.children[1].reaction.type).toBe('chat_reply');
  });

  test('_counterCaseRole wraps a role-locked case as if(role) then seq else chat_reply', () => {
    const c = _counterCaseRole('reset', ['broadcaster'], { type: 'counter', action: 'reset', name: 'x' }, 'ok', 'no');
    expect(c.equals).toBe('reset');
    expect(c.then.kind).toBe('if');
    expect(c.then.when.kind).toBe('leaf');
    expect(c.then.when.condition.type).toBe('role');
    expect(c.then.when.condition.roles).toEqual(['broadcaster']);
    expect(c.then.then.kind).toBe('seq');
    expect(c.then.then.children).toHaveLength(2);
    expect(c.then.then.children[0].reaction.type).toBe('counter');
    expect(c.then.then.children[1].reaction.type).toBe('chat_reply');
    expect(c.then.else.kind).toBe('reaction');
    expect(c.then.else.reaction.message).toBe('no');
  });
});

describe('_buildCounterSwitch', () => {
  test('builds a switch with 8 cases + default, query default, role wraps', () => {
    const sw = _buildCounterSwitch('deaths');
    expect(sw.kind).toBe('switch');
    expect(sw.on).toBe('{args[0]}');
    expect(sw.cases).toHaveLength(8);
    const equals = sw.cases.map(c => c.equals);
    expect(equals).toEqual(['+', '-', 'set', 'reset', 'add', 'select', 'clear', 'delsub']);
    // free cases (+/-)
    expect(sw.cases[0].then.kind).toBe('seq');
    expect(sw.cases[1].then.kind).toBe('seq');
    // role-locked cases
    const setCase = sw.cases.find(c => c.equals === 'set');
    expect(setCase.then.kind).toBe('if');
    expect(setCase.then.when.condition.roles).toEqual(['mod', 'broadcaster']);
    const resetCase = sw.cases.find(c => c.equals === 'reset');
    expect(resetCase.then.when.condition.roles).toEqual(['broadcaster']);
    const delsubCase = sw.cases.find(c => c.equals === 'delsub');
    expect(delsubCase.then.when.condition.roles).toEqual(['broadcaster']);
    // default = query seq
    expect(sw.default.kind).toBe('seq');
    expect(sw.default.children[0].reaction.action).toBe('query');
    expect(sw.default.children[0].reaction.name).toBe('deaths');
    expect(sw.default.children[0].reaction.category_dependent).toBe(false);
  });

  test('increment case amount is {args[1]} placeholder', () => {
    const sw = _buildCounterSwitch('deaths');
    const incCase = sw.cases.find(c => c.equals === '+');
    expect(incCase.then.children[0].reaction.action).toBe('increment');
    expect(incCase.then.children[0].reaction.amount).toBe('{args[1]}');
  });
});

describe('_counterReactionOf', () => {
  test('finds the first counter leaf in a switch reactions tree', () => {
    const cmd = { reactions: _buildCounterSwitch('deaths') };
    const reaction = _counterReactionOf(cmd);
    expect(reaction).toBeTruthy();
    expect(reaction.type).toBe('counter');
    expect(reaction.name).toBe('deaths');
  });

  test('returns null when no counter leaf exists', () => {
    const cmd = { reactions: { kind: 'seq', children: [{ kind: 'reaction', reaction: { type: 'chat_reply', message: 'hi' } }] } };
    expect(_counterReactionOf(cmd)).toBeNull();
  });
});

describe('createNewCounter', () => {
  let originalGetElementById;
  let originalFetch;
  beforeEach(() => {
    global.jsonBuffer = { commands: [] };
    originalGetElementById = document.getElementById.bind(document);
    originalFetch = global.fetch;
    document.getElementById = (id) => {
      const el = _stubElement();
      el.innerHTML = '';
      if (id === 'commandList' || id === 'commandEditor') return el;
      return originalGetElementById(id);
    };
  });
  afterEach(() => {
    delete global.jsonBuffer;
    document.getElementById = originalGetElementById;
    if (originalFetch === undefined) delete global.fetch; else global.fetch = originalFetch;
    if (global.window) global.window.prompt = undefined;
  });

  test('prompts for a name and pushes one switch trigger', () => {
    global.window.prompt = () => 'deaths';
    global.fetch = () => Promise.resolve({ json: () => Promise.resolve({}) });
    const cmd = createNewCounter();
    expect(cmd).toBeTruthy();
    expect(global.jsonBuffer.commands).toHaveLength(1);
    expect(cmd.name).toBe('deaths');
    expect(cmd.when.kind).toBe('and');
    expect(cmd.when.children[0].condition.type).toBe('command');
    expect(cmd.when.children[0].condition.command).toBe('!deaths');
    expect(cmd.reactions.kind).toBe('switch');
    expect(cmd.reactions.on).toBe('{args[0]}');
    expect(cmd.reactions.cases).toHaveLength(8);
    expect(cmd.roles).toEqual([]);
  });

  test('returns null when prompt is cancelled', () => {
    global.window.prompt = () => null;
    expect(createNewCounter()).toBeNull();
    expect(global.jsonBuffer.commands).toHaveLength(0);
  });

  test('returns null when name is blank', () => {
    global.window.prompt = () => '   ';
    expect(createNewCounter()).toBeNull();
  });
});

describe('renameCounter', () => {
  test('renames the counter reaction name and command leaf', () => {
    const cmd = { name: 'deaths', reactions: _buildCounterSwitch('deaths') };
    cmd.when = { kind: 'and', children: [{ kind: 'leaf', condition: { type: 'command', command: '!deaths' } }] };
    global.window.prompt = () => 'kills';
    const newName = renameCounter(cmd);
    expect(newName).toBe('kills');
    const reaction = _counterReactionOf(cmd);
    expect(reaction.name).toBe('kills');
    expect(cmd.when.children[0].condition.command).toBe('!kills');
    expect(cmd.name).toBe('kills');
    delete global.window.prompt;
  });

  test('returns null when prompt cancelled', () => {
    const cmd = { name: 'deaths', reactions: _buildCounterSwitch('deaths') };
    global.window.prompt = () => null;
    expect(renameCounter(cmd)).toBeNull();
    delete global.window.prompt;
  });
});

describe('deleteCounter', () => {
  test('removes the command from jsonBuffer', () => {
    const cmd = { name: 'deaths', reactions: _buildCounterSwitch('deaths') };
    global.jsonBuffer = { commands: [cmd] };
    expect(deleteCounter(cmd)).toBe(true);
    expect(global.jsonBuffer.commands).toHaveLength(0);
    delete global.jsonBuffer;
  });

  test('returns false when command not in buffer', () => {
    const cmd = { name: 'x' };
    global.jsonBuffer = { commands: [] };
    expect(deleteCounter(cmd)).toBe(false);
    delete global.jsonBuffer;
  });
});
