"""Runtime-test the addon against tiny WoW API stubs (no game required)."""
import sys
from pathlib import Path

from lupa import LuaRuntime

PRELUDE = r"""
_G._messages = {}
_G._fonts = {}
function _obj()
  local o = {}
  o._shown = false
  function o:SetSize(w, h) self.w, self.h = w, h end
  function o:SetPoint(...) self.point = {...} end
  function o:SetFrameStrata() end
  function o:SetToplevel() end
  function o:SetClampedToScreen() end
  function o:SetMovable() end
  function o:EnableMouse() end
  function o:RegisterForDrag() end
  function o:SetScript(name, fn) self.scripts = self.scripts or {}; self.scripts[name] = fn end
  function o:GetScript(name) return self.scripts and self.scripts[name] end
  function o:SetBackdrop() end
  function o:SetBackdropColor() end
  function o:SetBackdropBorderColor() end
  function o:CreateFontString()
    local fs = _obj()
    _G._fonts[#_G._fonts + 1] = fs
    return fs
  end
  function o:GetCenter() return 100, 100 end
  function o:Show()
    self._shown = true
    if self.scripts and self.scripts.OnShow then self.scripts.OnShow(self) end
  end
  function o:Hide() self._shown = false end
  function o:IsShown() return self._shown end
  function o:SetText(t) self.text = t end
  function o:GetText() return self.text end
  function o:SetChecked(v) self.checked = v end
  function o:GetChecked() return self.checked end
  function o:SetWidth(w) self.w = w end
  function o:SetJustifyH() end
  function o:SetTextColor() end
  function o:RegisterEvent(e) self.event = e end
  function o:AddMessage(m) _G._messages[#_G._messages + 1] = m end
  function o:SetOwner() end
  function o:AddLine() end
  return o
end
UIParent = _obj()
DEFAULT_CHAT_FRAME = _obj()
GameTooltip = _obj()
SlashCmdList = {}
function CreateFrame(kind, name, parent, template)
  local f = _obj()
  f.kind = kind
  if name then _G[name] = f end
  _G._last_frame = f
  return f
end
function ReloadUI() _G._reloaded = true end
time = os.time
"""


def main() -> int:
    lua = LuaRuntime()
    source = (Path("addon/WoWVoice/WoWVoice.lua")).read_text(encoding="utf-8")
    lua.execute(PRELUDE)
    lua.execute(source)

    events = lua.eval("_G._last_frame")
    events.scripts["OnEvent"](events, "ADDON_LOADED", "WoWVoice")

    failures = 0

    def check(label, condition, detail=""):
        nonlocal failures
        if condition:
            print(f"ok   {label}")
        else:
            failures += 1
            print(f"FAIL {label} {detail}")

    db = lua.eval("WoWVoiceDB")
    check("defaults created", db["defaultChannel"] == "say" and db["sticky"] is True)
    check("panel hidden at load", lua.eval("WoWVoicePanel:IsShown()") is False)

    lua.eval('SlashCmdList["WOWVOICE"]("status state=running | channel=Party | mic=Test Mic | last=hello there")')
    check("status stored", lua.eval("WoWVoiceDB.status").startswith("state=running"))
    check("status time set", lua.eval("WoWVoiceDB.statusTime") > 0)

    lua.eval('SlashCmdList["WOWVOICE"]("show")')
    check("show opens panel", lua.eval("WoWVoicePanel:IsShown()") is True)
    fonts = lua.eval("_G._fonts")
    texts = [fonts[i].text for i in range(1, len(fonts) + 1) if fonts[i].text]
    check("status headline rendered", any("Tool running" in t for t in texts), texts)
    check("channel rendered", any("Channel: Party" in t for t in texts), texts)
    check("last message rendered", any("Last: hello there" in t for t in texts), texts)

    lua.eval('SlashCmdList["WOWVOICE"]("hide")')
    check("hide closes panel", lua.eval("WoWVoicePanel:IsShown()") is False)

    lua.eval('WoWVoice_Toggle()')
    check("binding toggles panel", lua.eval("WoWVoicePanel:IsShown()") is True)

    lua.eval('SlashCmdList["WOWVOICE"]("bogus")')
    check("help printed", any("commands:" in m for m in lua.eval("_G._messages").values()))

    print()
    print(f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
