/**
 * Central frontend label/hint map for the Config-UI.
 *
 * Display names (German) for trigger/reaction types and AST node kinds, plus
 * matching hints and placeholder documentation. The backend ``TRIGGER_HINTS``
 * (UI.py) keeps scope/freigabe info; this file owns the user-facing display
 * text and examples. Structured for a future i18n swap.
 */

const LABELS = {
    triggerTypes: {
        command: 'Chat-Befehl',
        time: 'Timer',
        channel_point_reward: 'Channel-Punkte-Belohnung',
        first_time_chatter: 'Erstmaliger Chatter (Twitch-Flag)',
        new_chatter: 'Neuer Chatter (Inaktivitäts-Zeitfenster)',
        follow: 'Follow',
        sub: 'Abo',
        cheer: 'Cheer',
        raid: 'Raid',
        compare: 'Vergleich',
        role: 'Rolle'
    },
    reactionTypes: {
        chat_reply: 'Chat-Nachricht',
        overlay_text: 'Overlay-Text',
        overlay_gif: 'Overlay-GIF',
        clip: 'Clip erstellen',
        counter: 'Zähler',
        moderation: 'Moderation',
        streampet: 'StreamPet'
    },
    nodeKinds: {
        and: 'Alle (UND)',
        or: 'Mindestens eines (ODER)',
        not: 'Nicht',
        leaf: 'Bedingung',
        seq: 'Reihenfolge',
        if: 'Wenn/Dann/Sonst',
        switch: 'Fallunterscheidung',
        reaction: 'Aktion'
    },
    fields: {
        command: 'Befehl',
        interval_minutes: 'Intervall (Minuten)',
        reward_id: 'Reward-ID',
        time: 'Zeitfenster (Sekunden)',
        min_bits: 'Min. Bits',
        min_viewers: 'Min. Zuschauer',
        field: 'Feld',
        op: 'Operator',
        value: 'Wert',
        message: 'Nachricht',
        text: 'Text',
        gif_id: 'GIF-ID',
        action: 'Aktion',
        name: 'Name',
        target: 'Ziel-User',
        username: 'Username'
    },
    hints: {
        command: {
            match: 'Matchet den Chat-Text ab dem Anfang, Groß-/Kleinschreibung wird ignoriert. Alles nach dem Befehl wird als Argumente ({args[0]}, {args[1]}, ...) übernommen.',
            example: 'Beispiel `!timeout {target} {args[1]} 30` — {target} = {args[0]} = erster Parameter (z. B. User), {args[1]} = Grund.'
        },
        banme: {
            example: 'Beispiel `!banme`: Reaktion `moderation` Aktion `ban` mit Ziel {username} bannt den Auslöser; ein anderer Nutzer führt `!timeout {target} 60` aus.'
        },
        new_chatter: {
            match: 'Matchet, wenn der Chatter länger als `time` Sekunden nicht gesprochen hat (oder noch nie).'
        },
        first_time_chatter: {
            match: 'Matchet, wenn Twitch den Chatter als erstmalig markiert (chatter_is_new-Flag). Keine Konfiguration nötig.'
        },
        counter: 'Counter-Platzhalter in Chat-/Overlay-Texten: {counter:name:value} (Wert), {counter:name:subcounter_value} (Wert des aktiven Subcounters, sonst 0), {counter:name:subcounter_label} (" (subname: wert)" bei aktivem Subcounter, sonst ""). Ein Counter besteht typischerweise aus einem Befehl mit switch über {args[0]} (Sub-Befehle +/−/set/reset/add/select/clear/delsub, default = query). category_dependent=ON: Counter-Category = aktuelle Twitch-Stream-Kategorie (game_name via GET /channels, nur production; sonst "default"); OFF: statisches category-Feld. Auto-Create: fehlende Counter werden bei increment/decrement/set/query/add_subcounter/select/clear/delsub automatisch angelegt (nicht bei delete).',
        role: 'Rollen-Leaf: prüft die Rollen des Auslösers (mod/broadcaster/vip/subscriber). Broadcaster darf immer (System-Standard). Leere Rollen = keine Einschränkung. Primär für if.when im Reaktionsbaum, um pro Switch-Case Rollen zu erzwingen (der Scaffolder verriegelt delsub/reset für Broadcaster, set/add/select/clear für Mods).',
        placeholders: [
            { token: '{username}', meaning: 'Name des auslösenden Nutzers.' },
            { token: '{args[N]}', meaning: 'N-tes Argument des Befehls (0-basiert). Fehlt es, bleibt der Token stehen.' },
            { token: '{target}', meaning: 'Alias für {args[0]} (erstes Argument).' },
            { token: '{counter:name:value}', meaning: 'Zähler-Wert (z. B. {counter:deaths:value}).' },
            { token: '{counter:name:subcounter_value}', meaning: 'Wert des aktiven Subcounters (0 wenn keiner aktiv).' },
            { token: '{counter:name:subcounter_label}', meaning: '" (subname: wert)" bei aktivem Subcounter, sonst "".' },
            { token: '{counter:name:name}', meaning: 'Name des Zählers.' },
            { token: '{channel}', meaning: 'Kanal-Name aus dem Payload/Kontext.' },
            { token: '{event_name}', meaning: 'Name des auslösenden Events.' }
        ]
    }
};

/**
 * Return the display label for a (section, key) pair, falling back to the key
 * (or an explicit fallback) when no entry exists.
 *
 * @param {string} section - LABELS sub-object key (e.g. 'triggerTypes').
 * @param {string} key - key inside the section.
 * @param {string} [fallback] - optional fallback; defaults to the key itself.
 * @returns {string} the resolved display string.
 */
function displayLabel(section, key, fallback) {
    const sectionMap = LABELS[section];
    if (sectionMap && Object.prototype.hasOwnProperty.call(sectionMap, key)) {
        return sectionMap[key];
    }
    return fallback != null ? fallback : key;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        LABELS,
        displayLabel
    };
}
