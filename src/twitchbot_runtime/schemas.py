from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

TriggerType = Literal[
    "command",
    "time",
    "channel_point_reward",
    "first_time_chatter",
    "new_chatter",
    "follow",
    "sub",
    "cheer",
    "raid",
    "compare",
    "role",
]
ReactionType = Literal[
    "chat_reply",
    "overlay_text",
    "overlay_gif",
    "clip",
    "counter",
    "moderation",
    "streampet",
]
CompareOp = Literal["==", "!=", ">", ">=", "<", "<=", "in", "contains", "regex"]
RoleType = Literal["everyone", "subscriber", "vip", "mod", "broadcaster"]


class TriggerCondition(BaseModel):
    type: TriggerType = Field(
        ...,
        description=(
            "Type of the trigger condition. 'command' fires on a chat command, "
            "'time' fires on a timer interval, 'channel_point_reward' fires when a "
            "channel point reward is redeemed, 'first_time_chatter' fires when "
            "Twitch marks a chatter as first-time (chatter_is_new EventSub flag, "
            "no configuration needed), 'new_chatter' fires for a chatter whose last "
            "chat message is older than 'time' seconds (inactivity window) or who "
            "has never spoken before, 'follow' fires on a channel follow, 'sub' "
            "fires on a subscription, 'cheer' fires on a cheer (bits) optionally "
            "filtered by min_bits, 'raid' fires on an incoming raid optionally "
            "filtered by min_viewers, 'compare' is a generic comparison leaf "
            "(field/op/value) evaluated against resolved placeholders."
        ),
    )
    command: str | None = Field(
        None,
        description="Command text that triggers the condition, e.g. '!hello'. Required when type is 'command'.",
    )
    interval_minutes: float | None = Field(
        None,
        description="Interval in minutes between automatic executions. Required when type is 'time'.",
        gt=0,
    )
    reward_id: str | None = Field(
        None,
        description="Twitch channel point reward identifier. Required when type is 'channel_point_reward'.",
    )
    time: float | None = Field(
        None,
        description="Inactivity window in seconds for a 'new_chatter' condition: the chatter is considered new when their last message is older than this (or they have never spoken). Required when type is 'new_chatter'.",
        gt=0,
    )
    min_bits: int | None = Field(
        None,
        description="Minimum bits count for a 'cheer' condition to match (payload.bits >= min_bits). When omitted, any cheer matches.",
    )
    min_viewers: int | None = Field(
        None,
        description="Minimum viewers count for a 'raid' condition to match (payload.viewers >= min_viewers). When omitted, any raid matches.",
    )
    field: str | None = Field(
        None,
        description="Left-hand side of a 'compare' leaf. Placeholder-resolved (incl. {counter:...}, {args[N]}).",
    )
    op: CompareOp | None = Field(
        None,
        description="Comparison operator for a 'compare' leaf.",
    )
    value: Any = Field(
        None,
        description="Right-hand side of a 'compare' leaf (compared against the resolved field).",
    )
    roles: list[RoleType] | None = Field(
        None,
        description="Required roles for a 'role' leaf (mod/broadcaster/vip/subscriber). Empty or omitted = no restriction. Broadcaster always passes (matches the trigger-level role semantics).",
    )

    model_config = {"extra": "allow"}


class LeafNode(BaseModel):
    kind: Literal["leaf"] = Field(
        "leaf",
        description="Event/comparison leaf carrying a single condition payload.",
    )
    condition: TriggerCondition = Field(
        ...,
        description="The condition payload (one of the event types or a 'compare' leaf).",
    )

    model_config = {"extra": "allow"}


class AndNode(BaseModel):
    kind: Literal["and", "all"] = Field(
        "and",
        description="Logical AND: every child must match. 'all' is accepted as an alias.",
    )
    children: list[TriggerNode] = Field(
        default_factory=list,
        description="Ordered list of child trigger nodes; an empty list always matches.",
    )

    model_config = {"extra": "allow"}


class OrNode(BaseModel):
    kind: Literal["or", "any"] = Field(
        "or",
        description="Logical OR: at least one child must match. 'any' is accepted as an alias.",
    )
    children: list[TriggerNode] = Field(
        default_factory=list,
        description="Ordered list of child trigger nodes; an empty list never matches.",
    )

    model_config = {"extra": "allow"}


class NotNode(BaseModel):
    kind: Literal["not"] = Field(
        "not",
        description="Logical NOT: inverts the single child node.",
    )
    child: TriggerNode = Field(
        ...,
        description="The child trigger node to invert.",
    )

    model_config = {"extra": "allow"}


TriggerNode = Annotated[
    AndNode | OrNode | NotNode | LeafNode,
    Field(discriminator="kind"),
]


class ReactionData(BaseModel):
    animation: str | None = Field(
        None,
        description="Animation identifier (e.g. gif name) to play for overlay/streampet reactions.",
    )
    username: str | None = Field(
        None,
        description="Target Twitch username the reaction applies to. Populated by the ReactionEngine in the StreamPet data payload (runtime-resolved).",
    )
    color: str | None = Field(
        None,
        description="Color value (reserved; no overlay action consumes this field anymore).",
    )

    model_config = {"extra": "allow"}


class CommandReaction(BaseModel):
    type: ReactionType = Field(
        ...,
        description="Type of the Runtime reaction. 'chat_reply' posts a chat message, 'overlay_text' shows text on the overlay, 'overlay_gif' shows a gif on the overlay, 'clip' creates a Twitch clip, 'counter' manipulates a counter, 'moderation' performs a moderation action, 'streampet' triggers a StreamPet animation.",
    )
    message: str | None = Field(
        None,
        description="Chat message text. Used when type is 'chat_reply' (also for clip follow-up messages).",
    )
    text: str | None = Field(
        None,
        description="Text to render on the overlay. Used when type is 'overlay_text' or 'overlay_gif'.",
    )
    gif_id: str | None = Field(
        None,
        description="Gif identifier to render. Used when type is 'overlay_gif' (and as the animation id for 'streampet').",
    )
    action: str | None = Field(
        None,
        description="Action identifier. Used for 'counter' (e.g. increment/decrement/query), 'moderation' (e.g. target action), and the 'StreamPet' overlay action.",
    )
    channel: str | None = Field(
        None,
        description="Optional target channel for the reaction (defaults to the command context channel).",
    )
    data: ReactionData | None = Field(
        None,
        description="Structured payload for overlay actions such as 'StreamPet' (animation, username). username and the speech-bubble fields are populated productively by the ReactionEngine (runtime-resolved before dispatch).",
    )

    model_config = {"extra": "allow"}


class ReactionLeafNode(BaseModel):
    kind: Literal["reaction"] = Field(
        "reaction",
        description="A single reaction leaf carrying a Runtime reaction payload.",
    )
    reaction: CommandReaction = Field(
        ...,
        description="The Runtime reaction payload (one of chat_reply/overlay_text/.../streampet).",
    )

    model_config = {"extra": "allow"}


class SeqNode(BaseModel):
    kind: Literal["seq"] = Field(
        "seq",
        description="Sequential reaction group: every child is executed in order.",
    )
    children: list[ReactionNode] = Field(
        default_factory=list,
        description="Ordered list of child reaction-AST nodes.",
    )

    model_config = {"extra": "allow"}


class IfNode(BaseModel):
    kind: Literal["if"] = Field(
        "if",
        description="Conditional reaction: evaluates a trigger node (when) and executes then/else.",
    )
    when: TriggerNode = Field(
        ...,
        description="Trigger-tree condition (same format as a trigger's 'when'); uses engine-side placeholder resolution incl. {counter:...}.",
    )
    then: ReactionNode | None = Field(
        None,
        description="Reaction-AST executed when 'when' matches.",
    )
    else_: ReactionNode | None = Field(
        None,
        alias="else",
        description="Reaction-AST executed when 'when' does not match.",
    )

    model_config = {"extra": "allow", "populate_by_name": True}


class SwitchCase(BaseModel):
    equals: Any = Field(
        None,
        description="Value compared (as string) against the resolved 'on' expression.",
    )
    then: ReactionNode | None = Field(
        None,
        description="Reaction-AST executed when this case matches.",
    )

    model_config = {"extra": "allow"}


class SwitchNode(BaseModel):
    kind: Literal["switch"] = Field(
        "switch",
        description="Switch reaction: resolves 'on' (placeholder) and dispatches the first matching case, else 'default'.",
    )
    on: str = Field(
        "",
        description="Expression resolved with engine-side placeholders (incl. {args[N]}, {counter:...}).",
    )
    cases: list[SwitchCase] = Field(
        default_factory=list,
        description="Ordered list of cases; first match wins (string comparison).",
    )
    default: ReactionNode | None = Field(
        None,
        description="Reaction-AST executed when no case matches.",
    )

    model_config = {"extra": "allow"}


ReactionNode = Annotated[
    SeqNode | IfNode | SwitchNode | ReactionLeafNode,
    Field(discriminator="kind"),
]


class CommandSchema(BaseModel):
    name: str = Field(
        ...,
        description="Human-readable name of the trigger entry. Used as the primary identifier in the UI.",
    )
    event: str | None = Field(
        None,
        description="Optional event-name pre-filter applied before the 'when' tree is evaluated.",
    )
    when: TriggerNode = Field(
        default_factory=lambda: AndNode(kind="and"),
        description="Trigger tree (AND/OR/NOT/leaf) evaluated against the event. Replaces the legacy 'triggers' object.",
    )
    roles: list[RoleType] = Field(
        default_factory=list,
        description=(
            "Allowed roles that may invoke the trigger. 'mod' for moderators, "
            "'broadcaster' for the channel owner, 'vip' for VIPs, 'subscriber' "
            "for subscribers, 'everyone' for no restriction (equivalent to an "
            "empty list). Only chat-based triggers (command/new_chatter) "
            "receive roles from Twitch; for other trigger types a role filter "
            "other than 'everyone' effectively blocks all but broadcasters."
        ),
    )
    reactions: ReactionNode = Field(
        default_factory=lambda: SeqNode(kind="seq"),
        description="Reaction AST root (seq/if/switch/reaction) executed when the trigger matches. Replaces the legacy flat reactions list.",
    )

    model_config = {"extra": "allow"}


class CommandsDocument(BaseModel):
    commands: list[CommandSchema] = Field(
        default_factory=list,
        description="Full list of configured trigger entries persisted by the web UI.",
    )

    model_config = {"extra": "allow"}


def empty_command() -> dict[str, Any]:
    """
    @brief Build a default, UI-ready trigger entry as a plain dict.

    Produces a fresh "New command" template with a single ``command`` trigger
    leaf (command text "!new_command") wrapped in an ``and`` tree and an empty
    ``seq`` reaction root, used by the web UI when adding a new trigger row.

    @return: dict serialization of the default CommandSchema instance.
    """
    return CommandSchema.model_validate(
        {
            "name": "New command",
            "when": {
                "kind": "and",
                "children": [
                    {
                        "kind": "leaf",
                        "condition": {"type": "command", "command": "!new_command"},
                    }
                ],
            },
            "reactions": {"kind": "seq", "children": []},
            "roles": [],
        }
    ).model_dump(by_alias=True, exclude_none=False)
