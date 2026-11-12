# WoW Voice Chat

Push-to-talk chat for **World of Warcraft** on a controller. Press your chosen
button (Xbox Share by default), wait for the beep, say what you want, then press
it again. Your speech is transcribed locally and typed into the WoW chat box.

No cloud service, no account, no API key: speech recognition runs on your PC
with [faster-whisper](https://github.com/SYSTRAN/faster-whisper).

Built for the `_forever_` client, but it works with any WoW client that has the
normal chat box. A bundled in-game addon adds a small status/settings panel.

```
Button -> beep -> speak -> Button -> text appears in chat
```

## Is this allowed? Will I get banned?

**Short version:** it is designed to work like voice dictation for chat, and it
does not do the things Blizzard bans for. It is **not pre-approved** by
Blizzard, though, so no third-party tool can promise zero risk.

What it does **not** do:

- **No bots or unattended play.** Every message needs a fresh button press and a
  person speaking.
- **No multiboxing or input broadcasting.** One PC, one WoW client, one account.
- **No memory reading, DLL injection, packet editing, or game-file changes.**
  It does not hook or inject into `Wow.exe`. The addon uses only the normal
  addon API, stores settings, and draws a panel; it never sends chat itself.
- **No background automation.** It does not repeat messages or play the game
  for you.

The only "automation" is: one button press -> one spoken message -> one chat
line, typed with ordinary Windows keystrokes (the same way dictation software
works). Blizzard's enforcement targets bots, automated gameplay, input
broadcasting to multiple accounts, and cheats, not accessibility or chat input.
The 2021 [input-broadcasting policy](https://worldofwarcraft.blizzard.com/en-us/news/23558957)
is about mirroring one keystroke to multiple clients, which this tool does not
do.

To keep the risk low:

- Stay at the keyboard/controller; do not run it unattended.
- Do not use it to spam, repeat, or advertise.
- Do not extend it to gameplay actions (attacks, rotations, movement).
- Do not combine it with multiboxing or input-broadcasting software.

Blizzard's policies and enforcement can change, and this is not legal advice.
If you want zero third-party risk, do not use external input tools at all.

## Requirements

- Windows 10 or 11
- Python 3.12 with the **py launcher** ([python.org](https://www.python.org/downloads/))
- A controller that Windows sees as a gamepad/joystick, **or** any keyboard key.
  Xbox Share is the tested default; most PlayStation, Switch Pro, and 8BitDo
  controllers can be detected too.
- A microphone
- World of Warcraft

## Install

1. Download the latest **ZIP from the GitHub Releases page** and extract it
   somewhere you can write to (for example `Documents\WoWVoiceChat`, not
   `Program Files`).
2. Double-click **`setup.bat`**. It creates a private Python environment,
   installs the packages, downloads the speech model once (about 500 MB), and
   creates a desktop shortcut. If Python 3.12 is missing, setup offers to
   install it automatically with winget.
3. The setup window opens at the end. Choose:
   - **World of Warcraft folder** - use **Find**, or **Browse** and pick the
     folder that contains `Wow.exe` (for example
     `C:\Program Files (x86)\World of Warcraft\_forever_`).
   - **Microphone** - pick your headset from the list and press **Test**. It
     records 2.5 seconds and tells you whether it heard speech.
   - **Talk button** - see below.
   - **In-game panel** - press **Install / Update** to copy the addon into
     `Interface\AddOns`.
4. Press **Save & Finish**. The control panel opens; press **Start**, then switch
   to World of Warcraft. Next time, launch **WoW Voice Chat** from the desktop
   shortcut.

If **Install / Update** reports that Windows blocked the copy, close setup,
right-click **`setup.bat`** and choose **Run as administrator**, then press
**Install / Update** again.

If Windows' **Smart App Control** asks about Python or a DLL the first time,
allow it. It is a one-time reputation check.

## Changing the microphone or talk button

Open the control panel and press **Setup...** at any time. Everything can be
changed there, including after the first run.

### Talk button

The setup window offers three modes:

- **Controller button** - the Xbox Share button is already configured. For
  another controller, press **Detect button**.
- **Keyboard key** - choose F1-F12, Space, Tab, Mouse 4, or Mouse 5.
- **Both** - the controller button *and* a keyboard key work (handy for testing).

For a non-Xbox controller:

1. Choose **Controller button**.
2. Press **Detect button**, then press the button you want **three times**.
3. Press **Test** and press it a few more times. The wizard reports how many
   presses it saw.
4. If detection fails, open **Advanced** and use
   **`run.bat --raw-debug --seconds 30`**: press the button once and enter the
   byte/bit that changed.

Most controllers work this way, including PlayStation, Switch Pro, and 8BitDo
models. The controller must be visible to Windows as a HID device: **Steam
Input** or **DS4Windows** can hide or remap it. If your controller emulates a
keyboard instead, use the **Keyboard key** mode and bind that key.

The manual **Byte** and **Bit mask** fields are hidden under **Advanced** and
are not needed for normal setup.

## In-game panel (addon)

The addon is included in the ZIP and installed by the setup window. In game:

1. Type **`/reload`** (or restart WoW) so the addon loads.
2. Type **`/wvc`** to open the panel. You can also bind
   *Toggle WoWVoice Panel* in **Key Bindings**.
3. A circular button also sits by the minimap (bottom-left by default). Click
   it to open the panel, drag it around the minimap to move it, or hide it with
   **`/wvc minimap off`**.
4. Pick the default channel and toggle sticky/Escape behaviour.
5. Press **Save & Reload UI**. The addon saves on `/reload` or logout, and the
   desktop tool applies the new settings within a few seconds.

The panel shows the last status the desktop tool sent it. Use **Send status to
game** in the control panel to push the current state manually.

WoW addons cannot open sockets or read arbitrary files, so the two sides
communicate indirectly:

- **addon -> tool:** SavedVariables, written on `/reload` or logout.
- **tool -> addon:** a `/wvc status ...` line typed into chat.

Useful commands:

| Command | Effect |
| --- | --- |
| `/wvc` | Show or hide the panel |
| `/wvc show` / `/wvc hide` | Panel visibility |
| `/wvc minimap [on\|off\|reset]` | Show, hide, or move the minimap button |
| `/wvc reload` | Save and reload the UI |
| `/wvc status <text>` | Set the status line (used by the tool) |

## Using it

1. Press your talk button (**Share** on Xbox, or your chosen key). You hear a
   short beep.
2. Say your message. Start with a channel name to switch channels.
3. Press the talk button again. You hear a lower beep and the message is sent.

Examples (this is what the routing does with your speech):

| You say | Sent to WoW |
| --- | --- |
| "party hey what's up" | `/p hey what's up` |
| "hey what's up" (after the line above) | `/p hey what's up` |
| "guild raid at eight" | `/g raid at eight` |
| "raid warning pull now" | `/rw pull now` |
| "general anyone selling bags" | `/1 anyone selling bags` |
| "whisper Bob on my way" | `/w Bob on my way` |
| "reply got it" | `/r got it` |
| "emote waves" | `/e waves` |
| "party" (no message) | just switches the channel |

The channel is **sticky**: once you say "party", later messages go to party
until you name another channel. The current channel is shown in the control
panel and in the in-game panel.

If a message genuinely starts with a channel word, say **"literal"** first:
"literal trade chat is spammy" sends `/p trade chat is spammy` (in the current
channel).

### Built-in channels

Say / Party / Yell / Guild / Officer / Raid / Raid Warning / Instance /
General (`/1`) / Trade (`/2`) / Local Defense (`/3`) / Looking for Group (`/4`) /
World Defense (`/5`) / Whisper / Reply / Emote.

Channel numbers can differ between clients. Edit the `command` values in
`config.json` if `/5` is not World Defense on your client.

> **Testing tip:** use Say, party chat, or whispers while you try it out. Avoid
> accidentally broadcasting to a large channel.

## Control panel

- **Start / Stop** - loads the speech model and begins listening, or shuts down
  and frees the microphone.
- **Setup...** - game folder, microphone, talk button, addon installation.
- **Send status to game** - types `/wvc status ...` so the in-game panel updates.
- **Open config** - edits `config.json`.
- **Always on top** - keeps the window visible over the game.
- **Log** - live output, also written to `wow-voicechat.log`.

Only one panel opens at a time. Closing it stops the tool. If the shortcut is
missing, run `panel.bat`; `run.bat` starts the console version.

## How chat is sent

The tool focuses WoW, opens the chat box with Enter, types the line, sends with
Enter, then presses **Escape** once. This client leaves the chat box open after
a synthetic Enter, so the Escape is expected. If your client closes the box by
itself, set `chat.close_chat_after_send` to `false` (otherwise Escape opens the
game menu).

WoW and this tool must run at the same privilege level. Windows blocks
simulated keystrokes from a non-elevated app to an elevated game.

## Configuration

`config.json` is created on first run (or by the setup window). The setup window
is the safe way to change it; these are the useful keys:

```json
{
  "trigger": {
    "mode": "auto",          // auto, controller, or hotkey
    "hotkey": "F9",
    "share_byte": 12,        // controller HID report byte for Share
    "share_mask": 8          // bit inside that byte
  },
  "audio": {
    "input_device": null,    // null = Windows default, or a device index/name
    "max_record_seconds": 30,
    "min_record_seconds": 0.35
  },
  "stt": {
    "model": "small.en",     // tiny.en is faster, small.en is more accurate
    "device": "cpu",
    "compute_type": "int8"
  },
  "addon": {
    "enabled": true,
    "use_in_game_settings": true,   // addon settings override this file
    "push_status_on_start": false,  // type /wvc status when the tool starts
    "announce_status": false        // update the panel after every message
  },
  "chat": {
    "default_channel": "say",
    "sticky": true,
    "focus_wow": true,
    "input_mode": "type",           // type = Unicode typing, paste = clipboard
    "close_chat_after_send": true   // press Escape once after sending
  }
}
```

### Command line

```text
run.bat --setup                  first-run setup window
run.bat --devices                list microphones and check the controller
run.bat --trigger-test           test the button/hotkey without the speech model
run.bat --raw-debug              show raw controller reports
run.bat --dry-run                transcribe but print the chat line instead of sending
run.bat --hotkey-only            ignore the controller
run.bat --send-test "/p hello"   send a fixed line
```

The same flags work with `main.py`, for example
`.venv\Scripts\python.exe main.py --setup`.

## Troubleshooting

- **The controller button does nothing.** Press your keyboard fallback (F9 by
  default) to check the rest of the app, then run
  `run.bat --trigger-test --seconds 30`. Open the setup window and use
  **Detect button**. Make sure Steam Input is not remapping the controller.
- **"Could not find the WoW window".** Start WoW first. The app looks for
  `Wow.exe` with a window title containing "World of Warcraft".
- **Nothing appears in chat.** Do not leave the WoW chat box open before you
  press your talk button. Check that WoW is not running as administrator while
  this tool is not (or run both elevated).
- **"Nothing usable was heard".** Pick another microphone in **Setup...** and
  press **Test**. A quiet headset may need a higher Windows input level or a
  lower `audio.silence_dbfs` (for example `-60`).
- **The panel does not exist in game.** The addon must be installed into the
  correct client folder (`_forever_\Interface\AddOns\WoWVoice`). Use **Install /
  Update** in Setup, then `/reload`; if it still does not appear, restart WoW
  and make sure the addon is enabled on the character-select AddOns screen.
- **"Windows blocked the copy" when installing the addon.** The game folder is
  protected. Run `setup.bat` as administrator once and use **Install / Update**,
  or copy `addon\WoWVoice` into
  `...\World of Warcraft\_forever_\Interface\AddOns` manually.
- **Addon changes do not apply immediately.** The game only writes
  SavedVariables on `/reload` or logout. Press **Save & Reload UI** in the panel,
  then wait a few seconds.
- **Share also opens Xbox Game Bar or takes a screenshot.** Turn that shortcut
  off in Windows Settings -> Gaming -> Xbox Game Bar. The tool still receives
  the button.
- **First transcription is slow.** The model loads once at startup. On CPU each
  message takes roughly as long as it took to say; `tiny.en` is faster and less
  accurate.
- **Setup failed.** Read the message in the console window, then run
  `setup.bat` again. Python 3.12 must be installed with the `py` launcher.

## Privacy

Recordings stay in memory and are discarded after transcription. Audio never
leaves the PC; the speech model runs locally. The tool only writes to the WoW
chat box when you finish a recording.

## Files

```text
main.py                 entry point and command-line flags
control_panel.py        desktop Start/Stop window
setup.bat               one-time installer (venv, packages, model, shortcut)
panel.bat / run.bat     panel without shortcut / console version
make_shortcut.ps1       desktop shortcut creator
package.ps1             builds the release ZIP in dist\
selftest.py             routing checks that need no hardware
wowvoice/config.py      defaults and channel list
wowvoice/routing.py     spoken channel parser and sticky state
wowvoice/controller.py  controller button via Raw Input, hotkey fallback
wowvoice/recorder.py    microphone capture
wowvoice/transcriber.py local faster-whisper speech-to-text
wowvoice/wowinput.py    focus, keyboard input, chat delivery
wowvoice/app.py         push-to-talk state machine
wowvoice/addon_bridge.py SavedVariables parser, settings watcher, addon install
wowvoice/setup_wizard.py first-run setup window
addon/WoWVoice/         in-game panel and status/settings display
tests/                  unit and Lua smoke tests
```

## Development

```text
setup.bat
.venv\Scripts\python.exe selftest.py
.venv\Scripts\python.exe -m unittest discover -s tests
.venv\Scripts\python.exe tests\test_addon_lua.py   (needs: pip install lupa)
powershell -ExecutionPolicy Bypass -File package.ps1
```

`package.ps1` refuses to include `config.json`, the virtual environment, logs,
or PID files. Upload the resulting ZIP as a GitHub release asset.

### Releasing

Local build:

```text
powershell -ExecutionPolicy Bypass -File package.ps1
gh release create v1.0.2 dist\WoWVoiceChat-1.0.2.zip --title "WoWVoiceChat 1.0.2"
```

The GitHub Actions workflows run the tests on every push and build/upload the
ZIP automatically when you push a tag such as `v1.0.2`.

## License

MIT. See [LICENSE](LICENSE).
