from __future__ import annotations

import time
from typing import Any, cast

from ..logger import get_logger
from .events import normalize_event
from .verify import (
    extract_challenge,
    is_challenge_request,
    verify_signature,
)

logger = get_logger(__name__)


def create_webhook_app(bot: Any, webhook_secret: str):
    """Create a Flask app that receives Twitch EventSub webhooks.

    The app is intentionally minimal and self-contained: it never imports the
    overlay Flask app (separate process, separate port). Flask is imported
    lazily so importing this module does not require Flask at collection time.
    """
    from flask import Flask, jsonify, request

    app = Flask(__name__)

    @app.route("/eventsub", methods=["POST"])
    def eventsub_callback():
        body_text = request.get_data(as_text=True)
        headers = {k: v for k, v in request.headers.items()}

        message_id = headers.get("Twitch-Eventsub-Message-Id", "")
        message_timestamp = headers.get("Twitch-Eventsub-Message-Timestamp", "")
        signature = headers.get("Twitch-Eventsub-Message-Signature", "")

        if not verify_signature(
            message_id,
            message_timestamp,
            body_text,
            webhook_secret,
            signature,
            now=time.time(),
        ):
            logger.warning("EventSub signature verification failed for message_id=%s", message_id)
            return jsonify({"error": "invalid_signature"}), 403

        try:
            body = request.get_json(force=True, silent=False)
        except Exception:
            body = None

        if is_challenge_request(headers, body):
            challenge = extract_challenge(body)
            if challenge is None:
                return jsonify({"error": "missing_challenge"}), 400
            logger.info("EventSub challenge answered for subscription verification.")
            return challenge, 200, {"Content-Type": "text/plain"}

        if isinstance(body, dict):
            subscription = body.get("subscription") or {}
            subscription_type = subscription.get("type", "")
            event_payload = body.get("event") or {}
            try:
                event_name, payload = normalize_event(subscription_type, event_payload)
                bot.handle_event(event_name, payload)
            except Exception:
                logger.exception("Failed to dispatch EventSub event of type %s", subscription_type)

        return jsonify({"status": "ok"}), 202

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"}), 200

    return app


def run_webhook_server(
    bot: Any,
    webhook_secret: str,
    host: str = "127.0.0.1",
    port: int = 5002,
    *,
    block: bool = True,
) -> Any:
    """Start the EventSub webhook Flask server.

    When ``block`` is False the server runs in a background daemon thread so
    tests can start/stop it without blocking the main thread.
    """
    from werkzeug.serving import make_server

    app = create_webhook_app(bot, webhook_secret)

    server = make_server(host, port, app)

    if block:
        server.serve_forever()
        return server

    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    cast(Any, server)._kilo_thread = thread
    return server
