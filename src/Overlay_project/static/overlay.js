// =============================================================================
// StreamPet-Overlay — Browser-Client
// =============================================================================
// Rendert das StreamPet-GIF + Sprechblasen + temporäre Text-/GIF-Overlays auf
// einem <canvas>. Verbindet sich per Socket.IO mit dem Python-Overlay-Server.
//
// WICHTIG (Frame-Steuerung): Der Browser treibt die Anzeige-Frames lokal über
// requestAnimationFrame weiter, auch wenn Server-Updates ausbleiben. Der
// Server sendet ein `frame`-Feld im `update`-Payload (Rückwärtskompatibilität),
// dieses wird aber NICHT für die Darstellung verwendet — nur `animation`
// ist autoritativ für den Wechsel. Siehe P2-Entscheidung im Plan.
// =============================================================================

import { parseGIF, decompressFrames } from 'gifuct-js';

// ---------------------------------------------------------------------------
// Debug-Schalter
// ---------------------------------------------------------------------------
// Debug-Ausgaben sind standardmäßig aus. Aktivieren via:
//   - URL-Parameter ?debug=1  ODER
//   - config.debug === true
// Vermeidet Produktions-Störung (Debug-Box übermalt sonst das Overlay).
const urlParams = new URLSearchParams(window.location.search);
let DEBUG = urlParams.get('debug') === '1';

function logDebug(msg) {
    // Sichtbares Debug-<pre> nur im Debug-Modus beschreiben.
    if (!DEBUG) return;
    const el = document.getElementById("debug");
    if (el) el.textContent += msg + "\n";
}

// ---------------------------------------------------------------------------
// Canvas + globaler Zustand
// ---------------------------------------------------------------------------
const canvas = document.getElementById("overlay");
const ctx = canvas.getContext("2d");

let config = null;
let animations = {};         // { idle: { frames, width, height }, walk: ... }
let currentAnimation = "idle";
// currentFrame ist der LOKALE Frame-Counter, der pro draw() weiterschaltet.
// Er wird vom Server NICHT überschrieben (nur bei Animationswechsel auf 0).
let currentFrame = 0;
let petPosition = { x: 100, y: 100 };
let speechBubble = {
    text: "",
    visible: false,
    font: "Arial",
    fontSize: 20,
    x: 0,
    y: 0
};
let lastUpdate = "";
let lastFrameTime = performance.now();

// ---------------------------------------------------------------------------
// GIF-Laden (Hilfsfunktionen)
// ---------------------------------------------------------------------------
async function loadGIFFrames(path) {
    logDebug("Lade GIF: " + path);
    try {
        const res = await fetch(path);
        if (!res.ok) throw new Error("HTTP " + res.status);
        const buffer = await res.arrayBuffer();
        const parsedGif = parseGIF(buffer);
        const framesRaw = decompressFrames(parsedGif, true);

        const frames = await Promise.all(framesRaw.map(async frame => {
            const { width, height } = frame.dims;
            const imageData = new ImageData(
                new Uint8ClampedArray(frame.patch),
                width,
                height
            );
            return await createImageBitmap(imageData);
        }));

        logDebug(`Geladen: ${frames.length} Frames aus ${path}`);
        return {
            frames,
            width: framesRaw[0].dims.width,
            height: framesRaw[0].dims.height
        };
    } catch (error) {
        console.error("Fehler beim Laden des GIFs:", error);
        throw error;  // weiterwerfen, damit loadConfigAndImages retry/indikator kann
    }
}

async function loadJSON(path) {
    try {
        const response = await fetch(path);
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        return await response.json();
    } catch (e) {
        console.error("[loadJSON ERROR]", e);
        throw e;
    }
}

// ---------------------------------------------------------------------------
// Config + GIFs laden (mit Retry + sichtbarem Fehler)
// ---------------------------------------------------------------------------
const MAX_LOAD_RETRIES = 3;
const RETRY_DELAY_MS = 1000;

function drawErrorBanner(message) {
    // Sichtbarer Fehlerindikator im Canvas, statt still zu scheitern.
    // Hinweis: Fuer fehlendes/broken idle wird dieser NICHT mehr aufgerufen
    // (siehe loadConfigAndImages) — das Overlay laeuft transparent weiter
    // statt rot zu flackern. Beibehalten fuer andere (zukuenftige) Fehler.
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.font = "24px Arial";
    ctx.fillStyle = "red";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(message, canvas.width / 2, canvas.height / 2);
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
}

// Leere transparente Ein-Frame-Animation fuer den Fall, dass kein idle
// konfiguriert ist (config.idle fehlt/leer). Kein GIF-Zugriff, kein Banner.
async function makeEmptyIdleAnimation() {
    // ImageData(1,1) defaults to all-zero (transparent black).
    const bitmap = await createImageBitmap(new ImageData(1, 1));
    return { frames: [bitmap], width: 1, height: 1 };
}

async function loadConfigAndImages() {
    let attempt = 0;
    let configLoaded = false;
    while (attempt < MAX_LOAD_RETRIES) {
        attempt++;
        try {
            const response = await fetch("/config.json");
            if (!response.ok) throw new Error("HTTP " + response.status);
            config = await response.json();

            if (config.debug) DEBUG = true;

            const idlePath = config.idle;
            const animationPaths = config.animations;

            logDebug("Idle GIF Path: " + idlePath);
            logDebug("Animations: " + JSON.stringify(animationPaths));

            animations = {};
            // idle fehlt/leer -> synthetische leere Ein-Frame-Animation.
            // KEIN drawErrorBanner, KEIN Retry fuer diesen Fall.
            if (!idlePath) {
                animations["idle"] = await makeEmptyIdleAnimation();
                logDebug("Kein idle konfiguriert -> leere Ein-Frame-Animation.");
            } else {
                animations["idle"] = await loadGIFFrames(idlePath);
            }
            for (let key in (animationPaths || {})) {
                animations[key] = await loadGIFFrames(animationPaths[key]);
            }
            logDebug("Config und Animationen geladen.");
            configLoaded = true;
            return;  // Erfolg
        } catch (error) {
            console.error(`Ladeversuch ${attempt}/${MAX_LOAD_RETRIES} fehlgeschlagen:`, error);
            if (attempt < MAX_LOAD_RETRIES) {
                await new Promise(r => setTimeout(r, RETRY_DELAY_MS));
            }
        }
    }
    // Alle Versuche fehlgeschlagen. Wenn zumindest die Config geladen wurde,
    // ein leeres idle als letzteren Fallback hinterlegen, damit das Overlay
    // transparent weiterlaeuft (draw() bricht ab, wenn die aktuelle Animation
    // fehlt). Statt eines roten Banners nur console.error — kein Flackern.
    console.error("Overlay: Konfiguration/GIFs konnten nach " + MAX_LOAD_RETRIES + " Versuchen nicht geladen werden; Overlay laeuft transparent weiter.");
    if (config && !animations["idle"]) {
        try {
            animations["idle"] = await makeEmptyIdleAnimation();
        } catch (e) {
            console.error("Leere idle-Animation konnte nicht erzeugt werden:", e);
        }
    }
}

// ---------------------------------------------------------------------------
// Hilfsfunktion: abgerundetes Rechteck
// ---------------------------------------------------------------------------
function drawRoundedRect(x, y, width, height, radius) {
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + width - radius, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
    ctx.lineTo(x + width, y + height - radius);
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    ctx.lineTo(x + radius, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
}

// ---------------------------------------------------------------------------
// Socket.IO — Verbidungsaufbau
// ---------------------------------------------------------------------------
// URL dynamisch vom aktuellen Ursprung ableiten (kein hardkodierter Port).
// Produktion kann das Overlay hinter einem Proxy betreiben; localhost:5000
// bricht sonst.
const socket = io(window.location.origin, {
    reconnection: true,        // Socket.IO-Reconnect aktiv (Serverneustart -> auto)
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
});

// ---------------------------------------------------------------------------
// update-Event: Animationswechsel + Position + Sprechblase (NICHT den Frame)
// ---------------------------------------------------------------------------
socket.on("update", ({ stream_pet, messages }) => {
    if (!stream_pet) return;

    let { animation, position, scale, speech_bubble } = stream_pet;

    // Animationswechsel: nur wenn die neue Animation geladen ist und sich
    // tatsächlich unterscheidet. Setzt den lokalen Frame-Counter auf 0 zurück.
    // `frame` wird absichtlich NICHT übernommen (lokaler Counter autoritativ).
    if (animations[animation] && animation !== currentAnimation) {
        currentAnimation = animation;
        currentFrame = 0;
    }

    if (position) {
        petPosition.x = position.x;
        petPosition.y = position.y;
    }

    if (speech_bubble && speech_bubble.visible) {
        speechBubble = {
            text: speech_bubble.text,
            visible: true,
            font: speech_bubble.font,
            fontSize: speech_bubble.font_size,
            x: speech_bubble.position.x - petPosition.x,
            y: speech_bubble.position.y - petPosition.y
        };
    } else {
        speechBubble.visible = false;
    }

    if (DEBUG) {
        lastUpdate = `Anim: ${animation}, Position: (${position?.x}, ${position?.y})`;
    }

    if (messages && Array.isArray(messages)) {
        messages.forEach(msg => {
            if (typeof msg === 'object' && msg !== null) {
                if (msg.type === 'overlay_text' && msg.text) {
                    renderTextOverlay(msg.text);
                } else if (msg.type === 'overlay_gif' && msg.gif_id) {
                    renderGifOverlay(msg.gif_id, msg.text);
                }
            }
        });
    }
});

// ---------------------------------------------------------------------------
// Connect/Disconnect — Reconnect-Handling
// ---------------------------------------------------------------------------
socket.on("connect", () => {
    logDebug("Socket.IO verbunden.");
});

socket.on("disconnect", () => {
    logDebug("Socket.IO getrennt — Reconnect automatisch (Reconnection aktiv).");
    // requestAnimationFrame NICHT abbrechen: lokaler Frame-Counter läuft weiter,
    // Animation bleibt flüssig, auch wenn der Server kurz offline ist.
    // Canvas wird beim nächsten draw() weiter gezeichnet.
});

// ---------------------------------------------------------------------------
// Render-Loop (lokal, requestAnimationFrame)
// ---------------------------------------------------------------------------
let animationFrameId = null;

function loop() {
    draw();
    animationFrameId = requestAnimationFrame(loop);
}
animationFrameId = requestAnimationFrame(loop);

// ---------------------------------------------------------------------------
// Debug-Info (nur im Debug-Modus)
// ---------------------------------------------------------------------------
function drawDebugInfo() {
    if (!DEBUG) return;
    const anim = animations[currentAnimation];
    const frameCount = anim && anim.frames ? anim.frames.length : 0;
    ctx.font = "16px monospace";
    ctx.fillStyle = "rgba(0, 0, 0, 0.5)";
    ctx.fillRect(100, 10, 600, 90);
    ctx.fillStyle = "lime";
    ctx.fillText(lastUpdate, 110, 30);
    ctx.fillText(`FPS: ${Math.round(1000 / (performance.now() - lastFrameTime))} Anim: ${currentAnimation} (${frameCount} frames)`, 110, 80);
    lastFrameTime = performance.now();
}

// ---------------------------------------------------------------------------
// draw() — pro Frame: lokalen Counter weiterschalten + zeichnen
// ---------------------------------------------------------------------------
function draw() {
    if (!config || !animations[currentAnimation]) {
        return;
    }

    const anim = animations[currentAnimation];
    if (!anim || !anim.frames || anim.frames.length === 0) {
        return;
    }

    // Debug-Info NUR im Debug-Modus (sonst übermalt sie das Overlay).
    drawDebugInfo();

    // LOKALER Frame-Counter: pro draw() weiterschalten, vom Server unabhängig.
    // So läuft die Animation flüssig auch ohne Server-Updates.
    const image = anim.frames[currentFrame % anim.frames.length];

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const scale = canvas.width / 1920;
    const spc = (config && config.stream_pet_config) || {};
    const petScale = (spc.height || 300) * scale / (anim.height || 1);
    const width = image.width * petScale;
    const height = image.height * petScale;

    ctx.drawImage(image, petPosition.x, petPosition.y, width, height);

    // Sprechblase
    if (speechBubble.visible && speechBubble.text) {
        ctx.font = `${speechBubble.fontSize}px ${speechBubble.font}`;
        ctx.fillStyle = "rgba(0, 0, 0, 1)";
        ctx.strokeStyle = "black";
        ctx.lineWidth = 2;

        let text = speechBubble.text;
        let textWidth = ctx.measureText(text).width;
        const bubblePadding = 10;
        let bubbleWidth = textWidth + 2 * bubblePadding;
        let bubbleHeight = speechBubble.fontSize + 2 * bubblePadding;

        let x = petPosition.x + speechBubble.x;
        let y = petPosition.y + speechBubble.y;

        ctx.fillStyle = "rgba(255, 255, 255, 1)";
        drawRoundedRect(x, y, bubbleWidth, bubbleHeight, 8);
        ctx.fill();

        ctx.fillStyle = "black";
        ctx.strokeStyle = "white";
        ctx.lineWidth = 2;
        ctx.strokeText(text, x + bubblePadding, y + bubblePadding);
        ctx.fillText(text, x + bubblePadding, y + bubblePadding);
    }

    drawTextOverlays();

    // Lokalen Counter weiterschalten (für den NÄCHSTEN Frame).
    currentFrame = (currentFrame + 1) % anim.frames.length;
}

// ---------------------------------------------------------------------------
// Temporäre Overlays (overlay_text / overlay_gif)
// ---------------------------------------------------------------------------
// Server schickt bereits geprunte `messages` (TTL server-seitig via
// rendering_service._prune_messages). Die clientseitige `expires`-Logik ist
// ein zusätzlicher Anzeige-Timer; die Server-Source-of-Truth bleibt erhalten.
let textOverlays = [];

function renderTextOverlay(text) {
    textOverlays.push({
        text: text,
        gifId: null,
        expires: performance.now() + 5000
    });
}

function renderGifOverlay(gifId, text) {
    textOverlays.push({
        text: text || "",
        gifId: gifId,
        expires: performance.now() + 5000
    });
}

function drawTextOverlays() {
    const now = performance.now();
    textOverlays = textOverlays.filter(o => o.expires > now);
    if (textOverlays.length === 0) return;

    const scale = canvas.width / 1920;
    const fontSize = 24 * scale;
    ctx.font = `bold ${fontSize}px Arial`;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";

    let y = 20 * scale;
    for (const overlay of textOverlays) {
        if (overlay.gifId && animations[overlay.gifId]) {
            const anim = animations[overlay.gifId];
            const image = anim.frames[currentFrame % anim.frames.length];
            const gifWidth = image.width * scale;
            const gifHeight = image.height * scale;
            const gifX = canvas.width - gifWidth - 20 * scale;
            ctx.drawImage(image, gifX, y, gifWidth, gifHeight);
            if (overlay.text) {
                ctx.fillStyle = "black";
                ctx.lineWidth = 3 * scale;
                ctx.strokeStyle = "white";
                ctx.strokeText(overlay.text, canvas.width - (gifWidth / 2) - 20 * scale, y + gifHeight + 4 * scale);
                ctx.fillStyle = "white";
                ctx.fillText(overlay.text, canvas.width - (gifWidth / 2) - 20 * scale, y + gifHeight + 4 * scale);
            }
            y += gifHeight + (overlay.text ? fontSize + 16 * scale : 8 * scale);
        } else if (overlay.text) {
            ctx.fillStyle = "black";
            ctx.lineWidth = 3 * scale;
            ctx.strokeStyle = "white";
            ctx.strokeText(overlay.text, canvas.width / 2, y);
            ctx.fillStyle = "white";
            ctx.fillText(overlay.text, canvas.width / 2, y);
            y += fontSize + 8 * scale;
        }
    }

    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
(async () => {
    await loadConfigAndImages();
})();

// ---------------------------------------------------------------------------
// Globale Fehlerbehandlung
// ---------------------------------------------------------------------------
window.onerror = function (msg, url, lineNo, columnNo, error) {
    const string = `[JS ERROR] ${msg} at ${url}:${lineNo}:${columnNo}`;
    console.error(string);
    return false;
};

window.addEventListener("unhandledrejection", function(event) {
    console.error("[Promise ERROR]", event.reason);
});

logDebug("Loop started");
