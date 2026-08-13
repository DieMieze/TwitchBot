# Overlay (`src/Overlay_project/`)

Browser-rendered overlay driven by a Flask-SocketIO server plus a StreamPet
GIF engine. The runtime spawns this project as a `multiprocessing` subprocess
via `OverlayFacade`.

## Layout

- `overlay_server.py` — Flask-SocketIO server: serves the overlay HTML/JS and
  pushes action payloads to connected browsers over a WebSocket.
- `static/overlay.js` — browser client: advances StreamPet frames locally via
  `requestAnimationFrame` and renders text/GIF overlays.
- `StreamPet/` — `StreamPet.py` GIF engine (uses `gifuct-js` for decode, PIL
  optional for pre-render).
- `Stream_Pet.json` — StreamPet config (idle GIF, animations, speech bubble,
  position/font; edited via the Config-UI and Pos-UI).

## Action payload contract (Runtime → Overlay)

Messages put on `facade.queue` are shaped `{"action": <type>, "data": {...}}`:

- `{"action": "StreamPet", "data": {"animation", "username", ...}}`
- `{"action": "overlay_text", "data": {"text"}}` (5s server-side TTL)
- `{"action": "overlay_gif", "data": {"gif_id", "text"}}`

## Frame control (client drives)

The browser advances frames locally via `requestAnimationFrame`. The server
sends a `frame` field in the `update` payload for backward compatibility but
the client ignores it for rendering — only `animation` is authoritative for
animation switches (resets the local counter to 0).

## Subprocess IPC (`OverlayFacade`)

`src/twitchbot_runtime/overlay/facade.py` starts the Overlay_project process
(`multiprocessing`, `spawn` on Windows / `fork` on POSIX).

- **`facade.queue`** (`multiprocessing.Queue`) — parent→child IPC carrying
  action payloads **and** the `"STOP"` control token.
- **`StreamPet.queue`** (`queue.Queue`, threading) — internal to the animation
  engine; `"STOP"` never reaches it.

### Stop strategy (cross-platform)

Primary stop is queue/event-driven:

1. `running_event.clear()` — `multiprocessing.Event`, visible across the
   process boundary; inner loops break on the next flag check.
2. `queue.put_nowait("STOP")` — triggers `socketio.stop()` so the blocking
   `websocket_handler.start()` returns.
3. `process.join(timeout=5)` — wait for clean exit.
4. `process.terminate()` — last-resort hard stop after timeout. POSIX =
   `SIGTERM` (child handler runs); Windows = `TerminateProcess` (hard kill).

No external `os.kill`/`SIGTERM` is sent from the parent (unreliable on Windows).

## Usage / build

```bash
cd src/Overlay_project
npm install
npm run build    # production bundle (overlay.bundle.js)
npm run dev      # watch mode
```

The overlay is a browser overlay — no server deploy is needed beyond running
the runtime. Configure the port via `runtime.overlay.port` (default 5000);
the runtime resolves and persists it on first run (when overlay enabled and
mode is production/test).
