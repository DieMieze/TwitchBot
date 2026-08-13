from .base import BaseFeature


class ModerationFeature(BaseFeature):
    """
    @brief Registered/activatable no-op shell for the moderation feature.

    Moderation is currently driven exclusively by trigger-configured
    ``moderation`` reactions in ``settings.json["triggers"]``, dispatched by
    ``ReactionEngine._execute_moderation`` via ``ModerationHandler``. This
    feature therefore produces no reactions from Twitch confirmation events
    (``user.ban``/``user.timeout``/``message.deleted``/``message.delete``) —
    those are confirmations of actions already executed, so reacting to them
    would double-execute.

    The feature remains registered and activatable (``enabled`` flag) so the
    reactivation path stays open: re-enable by overriding ``handles_event`` and
    ``handle`` (and restoring event→action inference) in a subclass or here.
    """

    def __init__(self, enabled: bool = False) -> None:
        super().__init__(enabled=enabled, name="moderation")
