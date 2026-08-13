class MockWebSocket {
  static instances = [];

  static reset() {
    MockWebSocket.instances.forEach((ws) => {
      ws._closed = true;
      ws.readyState = MockWebSocket.CLOSED;
    });
    MockWebSocket.instances = [];
  }

  static lastInstance() {
    return MockWebSocket.instances[MockWebSocket.instances.length - 1] || null;
  }

  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  constructor(url) {
    this.url = url;
    this.readyState = MockWebSocket.CONNECTING;
    this._sentMessages = [];
    this._closed = false;
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    MockWebSocket.instances.push(this);
    const self = this;
    setTimeout(() => {
      if (self._closed) return;
      self.readyState = MockWebSocket.OPEN;
      if (typeof self.onopen === 'function') self.onopen({ type: 'open' });
    }, 0);
  }

  send(data) {
    if (this.readyState !== MockWebSocket.OPEN) {
      throw new Error('WebSocket is not in OPEN state');
    }
    this._sentMessages.push(data);
  }

  close(code = 1000, reason = '') {
    if (this._closed) return;
    this._closed = true;
    this.readyState = MockWebSocket.CLOSED;
    if (typeof this.onclose === 'function') {
      this.onclose({ type: 'close', code, reason, wasClean: true });
    }
  }

  simulateMessage(data) {
    const payload = typeof data === 'string' ? data : JSON.stringify(data);
    if (typeof this.onmessage === 'function') {
      this.onmessage({ type: 'message', data: payload });
    }
  }

  getSentMessages() {
    return this._sentMessages.slice();
  }

  getLastSentMessage() {
    return this._sentMessages[this._sentMessages.length - 1] || null;
  }
}

function parseOverlayMessage(rawMessage) {
  let parsed;
  try {
    parsed = typeof rawMessage === 'string' ? JSON.parse(rawMessage) : rawMessage;
  } catch (err) {
    return null;
  }
  if (!parsed || typeof parsed !== 'object') return null;
  const action = parsed.action;
  const data = parsed.data || {};
  const result = { action, data, isStreamPet: false };
  if (action === 'StreamPet') {
    result.isStreamPet = true;
    result.animation = data.animation || 'idle';
    result.username = data.username || '';
    result.extraData = data;
  }
  return result;
}

function parseUpdateEvent(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const streamPet = payload.stream_pet;
  if (!streamPet) return null;
  return {
    animation: streamPet.animation,
    frame: streamPet.frame,
    position: streamPet.position,
    scale: streamPet.scale,
    speechBubble: streamPet.speech_bubble
      ? {
          text: streamPet.speech_bubble.text,
          visible: streamPet.speech_bubble.visible,
          font: streamPet.speech_bubble.font,
          fontSize: streamPet.speech_bubble.font_size,
          x: streamPet.speech_bubble.position.x,
          y: streamPet.speech_bubble.position.y,
        }
      : { visible: false },
    messages: payload.messages || [],
  };
}

function buildStreamPetMessage(animation, extraData = {}) {
  return {
    action: 'StreamPet',
    data: {
      animation,
      username: extraData.username || '',
      ...extraData,
    },
  };
}

function buildUpdateEvent(streamPetData) {
  return {
    stream_pet: {
      animation: streamPetData.animation || 'idle',
      frame: streamPetData.frame || 1,
      position: streamPetData.position || { x: 0, y: 0 },
      scale: streamPetData.scale || 1,
      speech_bubble: streamPetData.speech_bubble || {
        text: '',
        visible: false,
        position: { x: 0, y: 0 },
        font: 'Arial',
        font_size: 20,
      },
    },
    messages: streamPetData.messages || [],
  };
}

module.exports = {
  MockWebSocket,
  parseOverlayMessage,
  parseUpdateEvent,
  buildStreamPetMessage,
  buildUpdateEvent,
};
