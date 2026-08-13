require('@jest/globals');

const { LABELS, displayLabel } = require('../labels');

const {
  defaultTriggerTypes,
  defaultReactionTypes,
  TRIGGER_KINDS,
  REACTION_KINDS,
} = require('../commands');

describe('LABELS coverage', () => {
  test('every default trigger type has a display label', () => {
    defaultTriggerTypes.forEach((type) => {
      expect(LABELS.triggerTypes[type]).toBeTruthy();
    });
  });

  test('every default reaction type has a display label', () => {
    defaultReactionTypes.forEach((type) => {
      expect(LABELS.reactionTypes[type]).toBeTruthy();
    });
  });

  test('every trigger node kind has a display label', () => {
    TRIGGER_KINDS.forEach((kind) => {
      expect(LABELS.nodeKinds[kind]).toBeTruthy();
    });
  });

  test('every reaction node kind has a display label', () => {
    REACTION_KINDS.forEach((kind) => {
      expect(LABELS.nodeKinds[kind]).toBeTruthy();
    });
  });
});

describe('displayLabel', () => {
  test('returns the mapped display string', () => {
    expect(displayLabel('triggerTypes', 'command')).toBe('Chat-Befehl');
    expect(displayLabel('reactionTypes', 'chat_reply')).toBe('Chat-Nachricht');
    expect(displayLabel('nodeKinds', 'and')).toBe('Alle (UND)');
  });

  test('falls back to the key when no entry exists', () => {
    expect(displayLabel('triggerTypes', 'unknown')).toBe('unknown');
  });

  test('uses explicit fallback when provided and no entry', () => {
    expect(displayLabel('triggerTypes', 'unknown', 'Fallback')).toBe('Fallback');
  });

  test('returns fallback for an unknown section', () => {
    expect(displayLabel('missingSection', 'x', 'FB')).toBe('FB');
  });
});

describe('hints', () => {
  test('command match + example hints exist', () => {
    expect(LABELS.hints.command.match).toBeTruthy();
    expect(LABELS.hints.command.example).toBeTruthy();
  });

  test('new_chatter and first_time_chatter match hints exist', () => {
    expect(LABELS.hints.new_chatter.match).toBeTruthy();
    expect(LABELS.hints.first_time_chatter.match).toBeTruthy();
  });

  test('placeholders list contains the core tokens', () => {
    const tokens = LABELS.hints.placeholders.map((p) => p.token);
    expect(tokens).toContain('{username}');
    expect(tokens).toContain('{args[N]}');
    expect(tokens).toContain('{target}');
    expect(tokens).toContain('{counter:name:value}');
  });

  test('role trigger type has a display label and hint', () => {
    expect(LABELS.triggerTypes.role).toBeTruthy();
    expect(LABELS.hints.role).toBeTruthy();
  });
});
