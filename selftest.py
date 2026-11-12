"""Quick sanity checks that need no microphone or game."""
from __future__ import annotations

from sofassay.config import load_config
from sofassay.routing import Router


def main() -> int:
    cfg = load_config()
    router = Router(cfg, log=lambda msg: None)
    failures = 0

    def check(heard: str, expected: str, label: str) -> None:
        nonlocal failures
        routed = router.parse(heard)
        actual = routed.command if routed else None
        if actual == expected:
            print(f"ok   {label}: {heard!r} -> {actual!r}")
        else:
            failures += 1
            print(f"FAIL {label}: {heard!r} -> {actual!r}, expected {expected!r}")

    def reset() -> None:
        router.current = router.default_channel
        router.whisper_target = None

    reset()
    check("party hey what's up", "/p hey what's up", "channel")
    check("that was close", "/p that was close", "sticky")
    check("guild raid at eight", "/g raid at eight", "switch")
    check("raid warning pull now", "/rw pull now", "two-word alias")
    check("general anyone selling bags", "/1 anyone selling bags", "numeric channel")
    check("switch to channel 5 hello", "/5 hello", "spoken channel number")
    check("go to party hello", "/p hello", "soft prefix")
    check("emote waves", "/e waves", "emote")

    reset()
    check("whisper Bob hello there", "/w Bob hello there", "whisper")
    check("are you there", "/w Bob are you there", "sticky whisper")
    check("reply on my way", "/r on my way", "reply")
    check("answer got it", "/r got it", "reply alias")

    # Every configured channel must route to its own command.
    reset()
    for channel in cfg["chat"]["channels"]:
        if channel.get("needs_target"):
            check("whisper Bob hello", "/w Bob hello", f"channel/{channel['name']}")
            continue
        if channel["name"] == "reply":
            check("reply hello", "/r hello", "channel/reply")
            continue
        alias = channel.get("aliases", [channel["name"]])[0]
        check(f"{alias} hello", f"{channel['command']} hello", f"channel/{channel['name']}")

    reset()
    routed = router.parse("party")
    if routed and routed.body == "" and routed.channel_name == "party":
        print("ok   channel-only: 'party' -> switches channel")
    else:
        failures += 1
        print("FAIL channel-only")

    reset()
    long_body = "word " * 100
    routed = router.parse("party " + long_body)
    if routed and len(routed.command) <= 250:
        print(f"ok   length cap: {len(routed.command)} chars")
    else:
        failures += 1
        print("FAIL length cap")

    print()
    print(f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
