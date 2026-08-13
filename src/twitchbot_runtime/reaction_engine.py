from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .expression.condition_match import match_event_condition
from .expression.evaluator import evaluate_reaction_ast

_CONTEXT_PLACEHOLDER = re.compile(r"\{(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)\}")
_ARGS_PLACEHOLDER = re.compile(r"\{args\[(?P<index>\d+)\]\}")
_TARGET_PLACEHOLDER = re.compile(r"\{target\}")

_AST_KINDS = {"seq", "if", "switch", "reaction"}


class ReactionEngine:
    """Executes reaction payloads using configurable side-effect handlers."""

    # --- Member variables ---
    send_chat: Callable[[str, str], Any]  # outbound chat sender: (broadcaster_id, message)
    overlay_dispatch: Callable[[dict[str, Any]], Any]  # overlay action dispatcher
    create_clip: Callable[[], str]  # clip creator returning a clip URL or ""
    counter_handler: Callable[[str, dict[str, Any]], Any]  # counter action handler
    moderation_handler: Callable[[str, dict[str, Any]], Any]  # moderation action handler
    streampet_handler: Callable[[dict[str, Any]], Any]  # streampet animation handler
    speech_bubble_provider: Callable[[], dict[str, Any] | None]  # raw speech_bubble_text/toggle reader
    _stream_category_provider: Callable[[], str]  # returns the broadcaster's current game_name ("" when unavailable)
    _time_provider: Callable[[], float]  # injectable clock for if.when time leaves
    _chatter_tracker: Any  # optional ChatterTracker for if.when new_chatter leaves

    def __init__(
        self,
        send_chat: Callable[[str, str], Any],
        overlay_dispatch: Callable[[dict[str, Any]], Any],
        create_clip: Callable[[], str],
        counter_handler: Callable[[str, dict[str, Any]], Any],
        moderation_handler: Callable[[str, dict[str, Any]], Any],
        streampet_handler: Callable[[dict[str, Any]], Any],
        speech_bubble_provider: Callable[[], dict[str, Any] | None] | None = None,
        time_provider: Callable[[], float] | None = None,
        chatter_tracker: Any = None,
        stream_category_provider: Callable[[], str] | None = None,
    ) -> None:
        """
        @brief Construct a ReactionEngine with the supplied side-effect handlers.

        Each handler is a callable injected by the runtime/mode layer; the engine
        itself stays free of any Twitch-specific dependencies so it can be tested
        in isolation and reused across modes.

        @param send_chat: callable accepting (broadcaster_id, message) that sends
            a chat message to the channel.
        @param overlay_dispatch: callable accepting an overlay action payload dict
            that forwards it to the overlay backend.
        @param create_clip: callable taking no args and returning a clip URL string
            (or "" when no clip was created).
        @param counter_handler: callable accepting (action, payload) for counter
            operations (increment/decrement/set/query/...).
        @param moderation_handler: callable accepting (action, payload) for
            moderation operations (ban/timeout/delete/purge).
        @param streampet_handler: callable accepting a streampet payload dict that
            triggers a StreamPet animation.
        @param speech_bubble_provider: optional callable returning a dict with
            raw ``speech_bubble_text``/``speech_bubble_toggle`` (read parent-side
            from Stream_Pet.json); the engine resolves placeholders in the text
            and forwards the finished value to the overlay. None disables the
            runtime-side speech bubble path (the overlay falls back to its own
            config).
        @param time_provider: optional callable returning the current time in
            seconds; used by ``if.when`` ``time`` leaves during AST evaluation.
            Defaults to ``time.time``.
        @param chatter_tracker: optional ChatterTracker exposing
            ``is_new(channel, username, window, now)`` used by ``if.when``
            ``new_chatter`` (inactivity-window) leaves. When ``None`` the
            ``new_chatter`` leaf returns ``False``.
        @param stream_category_provider: optional callable returning the
            broadcaster's current Twitch stream ``game_name`` (used by
            counter reactions with ``category_dependent: true`` to key
            counters per game). ``None`` disables the runtime-side category
            resolution (the counter falls back to ``"default"``); test/silent
            modes inject a stub returning ``""``.
        @return: None
        """
        self.send_chat = send_chat
        self.overlay_dispatch = overlay_dispatch
        self.create_clip = create_clip
        self.counter_handler = counter_handler
        self.moderation_handler = moderation_handler
        self.streampet_handler = streampet_handler
        self.speech_bubble_provider = speech_bubble_provider or (lambda: None)
        self._stream_category_provider = stream_category_provider or (lambda: "")
        self._chatter_tracker = chatter_tracker
        if time_provider is None:
            import time as _time

            self._time_provider = _time.time
        else:
            self._time_provider = time_provider

    def execute(self, reactions: list[dict[str, Any]], context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        @brief Execute a list of reactions and collect their result payloads.

        Each item is either a reaction-AST root (recognizable by a ``kind``
        field — ``seq``/``if``/``switch``/``reaction``) which is evaluated via
        :func:`expression.evaluator.evaluate_reaction_ast`, or a plain
        reaction dict (``type``-based) dispatched to the type-specific handler
        as before. Existing reaction dicts use fields ``type/message/text/
        gif_id/action/channel/data`` — none is ``kind``, so the two paths do
        not collide.

        @param reactions: list of reaction items (AST root or plain dict).
        @param context: optional runtime context (channel, broadcaster_id,
            username, args, event_name, ...); defaults to an empty dict.
        @return: list of result dicts produced by each executed reaction, in
            the same order as the input reactions (skipped entries excluded).
        """
        context = context or {}
        executed: list[dict[str, Any]] = []

        for reaction in reactions:
            if reaction is None:
                continue

            if isinstance(reaction, dict) and "kind" in reaction and reaction.get("kind") in _AST_KINDS:
                results = evaluate_reaction_ast(reaction, context, self, self._resolve_placeholder_for(context))
                executed.extend(results)
                continue

            executed.append(self._dispatch_plain(reaction, context))

        return executed

    def _dispatch_plain(self, reaction: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a single plain (``type``-based) reaction dict."""
        reaction_type = reaction.get("type")
        if reaction_type == "chat_reply":
            return self._execute_chat_reply(reaction, context)
        if reaction_type == "overlay_text":
            return self._execute_overlay_text(reaction, context)
        if reaction_type == "overlay_gif":
            return self._execute_overlay_gif(reaction, context)
        if reaction_type == "clip":
            return self._execute_clip(reaction, context)
        if reaction_type == "counter":
            return self._execute_counter(reaction, context)
        if reaction_type == "moderation":
            return self._execute_moderation(reaction, context)
        if reaction_type == "streampet":
            return self._execute_streampet(reaction, context)
        if reaction_type == "webui":
            return {"type": "webui", "payload": {k: v for k, v in reaction.items() if k != "type"}}
        return {"type": "unknown", "reaction": reaction}

    def _resolve_placeholder_for(self, context: dict[str, Any]) -> Callable[[str], str]:
        """Return a placeholder-resolver callable bound to ``context``.

        Used by the reaction AST evaluator for IF/SWITCH and by ``compare``
        leaves inside ``if.when`` trees. Mirrors :meth:`_resolve_placeholders`
        (counter → args → target → context key) without duplicating the regexes.
        """
        return lambda text: self._resolve_placeholders(text, context)

    def _match_condition(
        self,
        condition: dict[str, Any],
        event_name: str,
        payload: dict[str, Any],
        trigger_name: str,
    ) -> bool:
        """Engine-side event-condition matcher for ``if.when`` event-type leaves."""
        return match_event_condition(
            condition,
            event_name,
            payload,
            trigger_name,
            time_provider=self._time_provider,
            last_trigger_times={},
            chatter_tracker=self._chatter_tracker,
        )
    def _execute_chat_reply(self, reaction: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """
        @brief Send a chat message reaction, resolving placeholders in the text.

        @param reaction: reaction dict with optional ``channel`` and ``message``
            fields.
        @param context: runtime context used for broadcaster id and placeholder
            resolution.
        @return: result dict describing the sent chat reply (channel + message).
        """
        channel = reaction.get("channel", context.get("channel", "#channel"))
        broadcaster_id = self._resolve_broadcaster_id(context)
        message = reaction.get("message", "")
        message = self._resolve_placeholders(message, context)
        self.send_chat(broadcaster_id, message)
        return {"type": "chat_reply", "channel": channel, "message": message}

    @staticmethod
    def _resolve_broadcaster_id(context: dict[str, Any]) -> str:
        """
        @brief Resolve the numeric broadcaster id from context, falling back to the channel name.

        @param context: runtime context possibly containing ``broadcaster_id``
            and ``channel``.
        @return: the broadcaster id as a string when present and truthy,
            otherwise the channel name (default ``#channel``).
        """
        broadcaster_id = context.get("broadcaster_id")
        if broadcaster_id is not None and str(broadcaster_id):
            return str(broadcaster_id)
        channel = context.get("channel", "#channel")
        return channel

    def _resolve_placeholders(self, message: str, context: dict[str, Any]) -> str:
        """
        @brief Resolve all placeholder tokens in a message string.

        Order of resolution: counter placeholders (delegated to the counter
        handler if it exposes ``resolve_placeholders``), ``{args[N]}``,
        ``{target}``, then generic ``{context_key}`` (e.g. ``{username}``).
        Unresolvable tokens are left intact.

        @param message: the raw message potentially containing placeholders.
        @param context: runtime context providing values for the placeholders.
        @return: the message with all resolvable placeholders substituted.
        """
        if not message:
            return message

        resolve_counter = getattr(self.counter_handler, "resolve_placeholders", None)
        if callable(resolve_counter):
            message = resolve_counter(message)

        message = self._resolve_args_placeholders(message, context)
        message = self._resolve_target_placeholder(message, context)

        def _replace_context(match: re.Match[str]) -> str:
            key = match.group("key")
            if key == "username":
                value = context.get("username", context.get("user_name", ""))
            else:
                value = context.get(key)
            if value is None:
                return match.group(0)
            return str(value)

        return _CONTEXT_PLACEHOLDER.sub(_replace_context, message)

    @staticmethod
    def _resolve_args_placeholders(message: str, context: dict[str, Any]) -> str:
        """
        @brief Replace ``{args[N]}`` tokens with the corresponding command argument.

        Out-of-range indices leave the token intact; the message is returned
        unchanged when no args are available.

        @param message: the message potentially containing ``{args[N]}`` tokens.
        @param context: runtime context whose ``args`` list supplies the values.
        @return: the message with resolvable ``{args[N]}`` tokens substituted.
        """
        args = context.get("args")
        if not isinstance(args, list) or not args:
            return message

        def _replace(match: re.Match[str]) -> str:
            index = int(match.group("index"))
            if index < 0 or index >= len(args):
                return match.group(0)
            return str(args[index])

        return _ARGS_PLACEHOLDER.sub(_replace, message)

    @staticmethod
    def _resolve_target_placeholder(message: str, context: dict[str, Any]) -> str:
        """
        @brief Replace ``{target}`` tokens with the first command argument.

        A convenience alias for ``{args[0]}``; the message is returned unchanged
        when no args are available.

        @param message: the message potentially containing ``{target}`` tokens.
        @param context: runtime context whose ``args`` list supplies the target.
        @return: the message with resolvable ``{target}`` tokens substituted.
        """
        args = context.get("args")
        if not isinstance(args, list) or not args:
            return message
        target_value = str(args[0])

        def _replace(match: re.Match[str]) -> str:
            return target_value

        return _TARGET_PLACEHOLDER.sub(_replace, message)

    def _execute_overlay_text(self, reaction: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """
        @brief Dispatch an overlay text action to the overlay backend.

        Placeholders in ``text`` are resolved with the same logic as
        ``chat_reply`` (``{username}``, ``{args[N]}``, ``{target}``,
        ``{counter:...}``).

        @param reaction: reaction dict with a ``text`` field to display.
        @param context: runtime context used for placeholder resolution.
        @return: result dict echoing the overlay text type and text value.
        """
        text = self._resolve_placeholders(reaction.get("text", ""), context)
        payload = {"action": "overlay_text", "data": {"text": text}}
        self.overlay_dispatch(payload)
        return {"type": "overlay_text", "text": text}

    def _execute_overlay_gif(self, reaction: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """
        @brief Dispatch an overlay gif action to the overlay backend.

        Placeholders in ``text`` are resolved with the same logic as
        ``chat_reply``.

        @param reaction: reaction dict with optional ``gif_id`` and ``text``
            fields.
        @param context: runtime context used for placeholder resolution.
        @return: result dict echoing the overlay gif type, gif_id and text.
        """
        gif_id = reaction.get("gif_id", "default")
        text = self._resolve_placeholders(reaction.get("text", ""), context)
        payload = {
            "action": "overlay_gif",
            "data": {
                "gif_id": gif_id,
                "text": text,
            },
        }
        self.overlay_dispatch(payload)
        return {"type": "overlay_gif", "gif_id": gif_id, "text": text}

    def _execute_clip(self, reaction: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """
        @brief Create a clip and announce it in chat when successful.

        @param reaction: reaction dict with an optional ``channel`` field.
        @param context: runtime context used for the broadcaster id and channel.
        @return: result dict with the clip URL on success, otherwise an error
            payload indicating no clip was created.
        """
        clip_url = self.create_clip()
        channel = reaction.get("channel", context.get("channel", "#channel"))
        broadcaster_id = self._resolve_broadcaster_id(context)
        if clip_url:
            self.send_chat(broadcaster_id, f"Clip erstellt: {clip_url}")
            return {"type": "clip", "clip_url": clip_url, "channel": channel}

        return {"type": "clip", "error": "no_clip_created"}

    def _execute_counter(self, reaction: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """
        @brief Delegate a counter action to the counter handler.

        Resolves the counter ``category`` (from the live stream category when
        ``category_dependent`` is set, otherwise from the static ``category``
        config field) and placeholder-resolves ``amount``/``value``/
        ``subcounter_name`` before dispatching. The static ``category`` is a
        config value and is NOT placeholder-resolved (dynamic category uses
        ``category_dependent: true``).

        @param reaction: reaction dict carrying the counter ``action`` and any
            additional fields the handler needs.
        @param context: runtime context used for placeholder resolution
            (``args``/``username``/``counter:...``).
        @return: result dict wrapping the counter handler's return value.
        """
        action = reaction.get("action", "query")
        if bool(reaction.get("category_dependent")):
            raw_category = self._stream_category_provider() or ""
        else:
            raw_category = reaction.get("category", "") or ""
        category = (str(raw_category)).strip() or "default"
        payload = {**reaction, "category": category}
        for field in ("amount", "value", "subcounter_name"):
            if field in payload and payload[field] is not None:
                payload[field] = self._resolve_placeholders(str(payload[field]), context)
        result = self.counter_handler(action, payload)
        return {"type": "counter", "result": result}

    def _execute_moderation(self, reaction: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """
        @brief Delegate a moderation action, resolving placeholders in the target.

        @param reaction: reaction dict carrying the moderation ``action`` and a
            ``target`` field (placeholder-resolved before dispatch).
        @param context: runtime context used for target placeholder resolution.
        @return: result dict wrapping the moderation handler's return value.
        """
        action = reaction.get("action", "none")
        payload = {**reaction}
        target = self._resolve_placeholders(payload.get("target", ""), context)
        payload["target"] = target
        result = self.moderation_handler(action, payload)
        return {"type": "moderation", "result": result}

    def _execute_streampet(self, reaction: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """
        @brief Trigger a StreamPet animation and mirror it to the overlay.

        Builds the overlay ``data`` dict with ``animation``/``event`` plus the
        context-derived ``username``/``args`` and the runtime-resolved speech
        bubble text + toggle. ``speech_bubble_text`` is read raw via the
        injected ``speech_bubble_provider`` (parent-side Stream_Pet.json) and
        fully resolved here (``{username}``/``{args[N]}``/``{counter:...}``)
        so the overlay becomes a pure renderer. The overlay gates visibility
        on ``speech_bubble_toggle`` + animation name itself.

        @param reaction: reaction dict with optional ``gif_id`` and ``event``
            fields.
        @param context: runtime context supplying the fallback ``event_name``,
            ``username``/``user_name`` and ``args``.
        @return: result dict wrapping the streampet handler's return value.
        """
        payload = {"gif_id": reaction.get("gif_id", "idle"), "event": reaction.get("event", context.get("event_name"))}
        result = self.streampet_handler(payload)

        username = context.get("username", context.get("user_name", ""))
        args = context.get("args", [])
        speech_bubble_text = ""
        speech_bubble_toggle = False
        provider = self.speech_bubble_provider
        if callable(provider):
            bubble_cfg = provider() or {}
            speech_bubble_text = self._resolve_placeholders(bubble_cfg.get("speech_bubble_text", "") or "", context)
            speech_bubble_toggle = bool(bubble_cfg.get("speech_bubble_toggle", False))

        data = {
            "animation": payload["gif_id"],
            "event": payload["event"],
            "username": username,
            "args": list(args) if isinstance(args, list) else [],
            "speech_bubble_text": speech_bubble_text,
            "speech_bubble_toggle": speech_bubble_toggle,
        }
        self.overlay_dispatch({"action": "StreamPet", "data": data})
        return {"type": "streampet", "result": result}
