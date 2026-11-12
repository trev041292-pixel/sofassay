"""Turn "party hey what's up" into a WoW chat command."""
from __future__ import annotations

import re
from dataclasses import dataclass

PREFIX_WORDS = {
    "switch",
    "change",
    "go",
    "to",
    "chat",
    "channel",
    "chan",
    "use",
    "in",
}

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

NAME_RE = re.compile(r"^[A-Za-z\u00C0-\u024F'\-]{1,16}$")


def _norm(token: str) -> str:
    return re.sub(r"[^a-z0-9']+", "", token.lower())


@dataclass
class RoutedMessage:
    channel_name: str
    label: str
    body: str
    command: str
    target: str | None = None
    explicit: bool = False


class Router:
    def __init__(self, cfg: dict, log=print):
        chat = cfg["chat"]
        self.channels = [dict(ch) for ch in chat["channels"]]
        self.sticky = bool(chat["sticky"])
        self.sticky_whisper = bool(chat.get("sticky_whisper", True))
        self.default_name = chat["default_channel"]
        self.default_channel = self._by_name(self.default_name) or self.channels[0]
        self.max_chars = int(chat.get("max_message_chars", 250))
        self.log = log

        self.alias_map: dict[str, dict] = {}
        for channel in self.channels:
            aliases = [channel["name"], *channel.get("aliases", [])]
            for alias in aliases:
                key = " ".join(_norm(part) for part in alias.split())
                if key:
                    self.alias_map[key] = channel
        self.max_alias_tokens = max(len(key.split()) for key in self.alias_map)

        self.current = self.default_channel
        self.whisper_target: str | None = None

    def _by_name(self, name: str) -> dict | None:
        for channel in self.channels:
            if channel["name"] == name:
                return channel
        return None

    @staticmethod
    def _clean_body(tokens: list[str]) -> str:
        tokens = [tok for tok in tokens if tok.strip()]
        if tokens:
            tokens[0] = re.sub(r"^[,;:.\-]+", "", tokens[0])
        return " ".join(tok for tok in tokens if tok).strip()

    def _ad_hoc_number(self, text: str) -> tuple[dict, str] | None:
        match = re.match(
            r"^(?:(?:switch|change|go)\s+to\s+|to\s+)?(?:chat\s+)?(?:channel|chan)\s+"
            r"(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")\b[,:;.\-]?\s*(.*)$",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        raw = match.group(1).lower()
        number = int(raw) if raw.isdigit() else NUMBER_WORDS[raw]
        if not 1 <= number <= 30:
            return None
        channel = {
            "name": f"channel{number}",
            "label": f"Channel {number}",
            "command": f"/{number}",
            "aliases": [],
        }
        return channel, match.group(2)

    def _find_channel(self, tokens: list[str]):
        """Find a leading channel alias, allowing a couple of soft prefixes."""
        best = None
        for skip in range(0, min(3, len(tokens))):
            if skip and _norm(tokens[skip - 1]) not in PREFIX_WORDS:
                break
            for size in range(1, self.max_alias_tokens + 1):
                end = skip + size
                if end > len(tokens):
                    break
                key = " ".join(_norm(tok) for tok in tokens[skip:end])
                channel = self.alias_map.get(key)
                if channel:
                    candidate = (skip, size, channel)
                    if best is None or (skip, -size) < (best[0], -best[1]):
                        best = candidate
        return best

    def parse(self, text: str) -> RoutedMessage | None:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return None

        if _norm(text.split()[0]) == "literal":
            body = self._clean_body(text.split()[1:])
            return self._compose(self.current, body, explicit=False)

        numbered = self._ad_hoc_number(text)
        if numbered:
            channel, remainder = numbered
            self.current = channel
            body = self._clean_body(remainder.split())
            return self._compose(channel, body, explicit=True)

        tokens = text.split()
        found = self._find_channel(tokens)
        if not found:
            return self._compose(self.current, self._clean_body(tokens), explicit=False)

        skip, size, channel = found
        remainder = tokens[skip + size :]
        target = None

        if channel.get("needs_target"):
            cleaned = list(remainder)
            if cleaned and _norm(cleaned[0]) == "to":
                cleaned = cleaned[1:]
            if cleaned:
                candidate = re.sub(r"^[,;:.\-]+|[,;:.\-]+$", "", cleaned[0])
                if NAME_RE.match(candidate):
                    target = candidate
                    remainder = cleaned[1:]
                else:
                    self.log(f"Could not understand whisper target: '{candidate}'")
                    return None
            elif self.whisper_target:
                target = self.whisper_target
            else:
                self.log("Heard 'whisper' but no character name.")
                return None
            self.whisper_target = target
        elif channel["name"] == "reply":
            if not remainder:
                return None

        if self.sticky:
            self.current = channel
        body = self._clean_body(remainder)
        return self._compose(channel, body, target=target, explicit=True)

    def _compose(
        self,
        channel: dict,
        body: str,
        target: str | None = None,
        explicit: bool = False,
    ) -> RoutedMessage | None:
        if channel.get("needs_target"):
            target = target or (self.whisper_target if self.sticky_whisper else None)
            if not target:
                return None
        prefix = channel["command"].format(target=target or "").strip()
        body = body.strip()
        room = self.max_chars - len(prefix) - 1
        if body and len(body) > max(0, room):
            body = body[: max(0, room)].rstrip()
        command = f"{prefix} {body}".strip() if body else prefix
        label = channel.get("label", channel["name"].replace("_", " ").title())
        if target:
            label = f"Whisper → {target}"
        return RoutedMessage(
            channel_name=channel["name"],
            label=label,
            body=body,
            command=command,
            target=target,
            explicit=explicit,
        )

    def describe(self) -> str:
        label = self.current.get("label", self.current["name"].title())
        if self.current.get("needs_target") and self.whisper_target:
            label = f"Whisper → {self.whisper_target}"
        return label

    def find_channel(self, name: str) -> dict | None:
        return self._by_name(str(name).strip().lower().replace(" ", ""))
