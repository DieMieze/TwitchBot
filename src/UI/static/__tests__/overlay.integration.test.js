require('@jest/globals');

const {
  MockWebSocket,
  parseOverlayMessage,
  parseUpdateEvent,
  buildStreamPetMessage,
  buildUpdateEvent,
} = require('./websocket.mock');

beforeEach(() => {
  MockWebSocket.reset();
});

describe('MockWebSocket', () => {
  test('opens connection asynchronously', () => {
    jest.useFakeTimers();
    try {
      const ws = new MockWebSocket('ws://localhost:5000');
      expect(ws.readyState).toBe(MockWebSocket.CONNECTING);
      const opened = jest.fn();
      ws.onopen = opened;
      jest.advanceTimersByTime(0);
      expect(opened).toHaveBeenCalledTimes(1);
      expect(ws.readyState).toBe(MockWebSocket.OPEN);
    } finally {
      jest.useRealTimers();
    }
  });

  test('records sent messages', async () => {
    const ws = new MockWebSocket('ws://localhost:5000');
    await open(ws);
    ws.send('hello');
    ws.send(JSON.stringify({ a: 1 }));
    expect(ws.getSentMessages()).toEqual(['hello', '{"a":1}']);
    expect(ws.getLastSentMessage()).toBe('{"a":1}');
  });

  test('throws when sending on non-open socket', () => {
    const ws = new MockWebSocket('ws://localhost:5000');
    expect(() => ws.send('early')).toThrow('not in OPEN state');
  });

  test('closes connection and fires onclose', () => {
    const ws = new MockWebSocket('ws://localhost:5000');
    const closed = jest.fn();
    ws.onclose = closed;
    ws.close(1000, 'done');
    expect(ws.readyState).toBe(MockWebSocket.CLOSED);
    expect(closed).toHaveBeenCalledWith(
      expect.objectContaining({ code: 1000, reason: 'done', wasClean: true })
    );
  });

  test('simulateMessage delivers payload to onmessage', async () => {
    const ws = new MockWebSocket('ws://localhost:5000');
    await open(ws);
    const received = jest.fn();
    ws.onmessage = received;
    ws.simulateMessage({ action: 'StreamPet', data: { animation: 'wave' } });
    expect(received).toHaveBeenCalledTimes(1);
    expect(received.mock.calls[0][0].data).toBe(
      JSON.stringify({ action: 'StreamPet', data: { animation: 'wave' } })
    );
  });

  test('tracks instances and provides lastInstance', () => {
    const a = new MockWebSocket('ws://a');
    const b = new MockWebSocket('ws://b');
    expect(MockWebSocket.lastInstance()).toBe(b);
    expect(MockWebSocket.instances).toHaveLength(2);
  });
});

describe('parseOverlayMessage - server-side message parsing (overlay.py:162-169)', () => {
  test('parses StreamPet action with animation', () => {
    const msg = buildStreamPetMessage('wave', { username: 'Mayle' });
    const parsed = parseOverlayMessage(msg);
    expect(parsed.action).toBe('StreamPet');
    expect(parsed.isStreamPet).toBe(true);
    expect(parsed.animation).toBe('wave');
    expect(parsed.username).toBe('Mayle');
  });

  test('parses StreamPet action defaulting animation to idle', () => {
    const parsed = parseOverlayMessage({ action: 'StreamPet', data: {} });
    expect(parsed.animation).toBe('idle');
    expect(parsed.username).toBe('');
  });

  test('parses unknown action as non-StreamPet', () => {
    const parsed = parseOverlayMessage({
      action: 'overlay_text',
      data: { text: 'Hi' },
    });
    expect(parsed.action).toBe('overlay_text');
    expect(parsed.isStreamPet).toBe(false);
  });

  test('returns null for invalid JSON string', () => {
    expect(parseOverlayMessage('not json')).toBeNull();
  });

  test('returns null for non-object input', () => {
    expect(parseOverlayMessage(null)).toBeNull();
    expect(parseOverlayMessage('')).toBeNull();
  });

  test('accepts raw object and JSON string', () => {
    const obj = { action: 'StreamPet', data: { animation: 'dance' } };
    expect(parseOverlayMessage(obj).animation).toBe('dance');
    expect(parseOverlayMessage(JSON.stringify(obj)).animation).toBe('dance');
  });
});

describe('parseUpdateEvent - client-side socket update (overlay.js:116-154)', () => {
  test('parses stream_pet update with animation and frame', () => {
    const evt = buildUpdateEvent({
      animation: 'wave',
      frame: 3,
      position: { x: 100, y: 200 },
      scale: 1.5,
    });
    const parsed = parseUpdateEvent(evt);
    expect(parsed.animation).toBe('wave');
    expect(parsed.frame).toBe(3);
    expect(parsed.position).toEqual({ x: 100, y: 200 });
    expect(parsed.scale).toBe(1.5);
  });

  test('parses visible speech bubble', () => {
    const evt = buildUpdateEvent({
      animation: 'wave',
      speech_bubble: {
        text: 'Hello!',
        visible: true,
        position: { x: 10, y: 20 },
        font: 'Arial',
        font_size: 24,
      },
    });
    const parsed = parseUpdateEvent(evt);
    expect(parsed.speechBubble.visible).toBe(true);
    expect(parsed.speechBubble.text).toBe('Hello!');
    expect(parsed.speechBubble.font).toBe('Arial');
    expect(parsed.speechBubble.fontSize).toBe(24);
    expect(parsed.speechBubble.x).toBe(10);
    expect(parsed.speechBubble.y).toBe(20);
  });

  test('returns hidden speech bubble when not provided', () => {
    const evt = buildUpdateEvent({ animation: 'idle' });
    const parsed = parseUpdateEvent(evt);
    expect(parsed.speechBubble.visible).toBe(false);
  });

  test('returns null when stream_pet missing', () => {
    expect(parseUpdateEvent({ messages: [] })).toBeNull();
    expect(parseUpdateEvent(null)).toBeNull();
  });

  test('defaults animation to idle and frame to 1', () => {
    const parsed = parseUpdateEvent(buildUpdateEvent({}));
    expect(parsed.animation).toBe('idle');
    expect(parsed.frame).toBe(1);
  });
});

describe('Overlay integration: WebSocket message round-trip', () => {
  test('server StreamPet message is parsed and rendered as update event', async () => {
    const ws = new MockWebSocket('ws://localhost:5000');
    await open(ws);

    const received = [];
    ws.onmessage = (event) => {
      const raw = JSON.parse(event.data);
      const parsed = parseOverlayMessage(raw);
      if (parsed && parsed.isStreamPet) {
        const rendered = buildUpdateEvent({
          animation: parsed.animation,
          frame: 1,
          position: { x: 50, y: 50 },
        });
        received.push(parseUpdateEvent(rendered));
      }
    };

    ws.simulateMessage(buildStreamPetMessage('wave', { username: 'MOCK_user_1' }));

    expect(received).toHaveLength(1);
    expect(received[0].animation).toBe('wave');
  });

  test('non-StreamPet messages are ignored by renderer', async () => {
    const ws = new MockWebSocket('ws://localhost:5000');
    await open(ws);

    let rendered = null;
    ws.onmessage = (event) => {
      const parsed = parseOverlayMessage(JSON.parse(event.data));
      if (parsed && parsed.isStreamPet) {
        rendered = parseUpdateEvent(buildUpdateEvent({ animation: parsed.animation }));
      }
    };

    ws.simulateMessage({ action: 'overlay_text', data: { text: 'Hi' } });
    expect(rendered).toBeNull();
  });

  test('multiple sequential StreamPet animations render in order', async () => {
    const ws = new MockWebSocket('ws://localhost:5000');
    await open(ws);

    const animations = [];
    ws.onmessage = (event) => {
      const parsed = parseOverlayMessage(JSON.parse(event.data));
      if (parsed && parsed.isStreamPet) {
        animations.push(parsed.animation);
      }
    };

    ['wave', 'dance', 'idle'].forEach((anim) => {
      ws.simulateMessage(buildStreamPetMessage(anim));
    });

    expect(animations).toEqual(['wave', 'dance', 'idle']);
  });

  test('connection lifecycle: open, exchange, close', async () => {
    const ws = new MockWebSocket('ws://localhost:5000');
    const events = [];
    ws.onopen = () => events.push('open');
    ws.onclose = () => events.push('close');

    await open(ws);
    ws.simulateMessage(buildStreamPetMessage('wave'));
    ws.close();

    expect(events).toEqual(['open', 'close']);
    expect(ws.getSentMessages()).toHaveLength(0);
  });
});

function open(ws) {
  return new Promise((resolve) => {
    const check = () => {
      if (ws.readyState === MockWebSocket.OPEN) {
        resolve();
      } else {
        setTimeout(check, 0);
      }
    };
    check();
  });
}
