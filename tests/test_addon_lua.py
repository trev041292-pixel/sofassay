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
  function o:SetTexture(texture) self.texture = texture end
  function o:SetTexCoord() end
  function o:SetVertexColor(r, g, b) self.vertex = {r, g, b} end
  function o:SetAlpha(a) self.alpha = a end
  function o:SetParent(p) self.parent = p end
  function o:SetFrameLevel(level) self.level = level end
  function o:RegisterForClicks() end
  function o:ClearAllPoints() self.point = nil end
  function o:CreateTexture()
    local texture = _obj()
    return texture
  end
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
Minimap = _obj()
function Minimap:GetWidth() return 140 end
function Minimap:GetHeight() return 140 end
function Minimap:GetEffectiveScale() return 1 end
function Minimap:GetFrameLevel() return 1 end
DEFAULT_CHAT_FRAME = _obj()
GameTooltip = _obj()
_G._tooltip = {}
function GameTooltip:AddLine(text) _G._tooltip[#_G._tooltip + 1] = tostring(text) end
function GameTooltip:SetText(text) _G._tooltip[#_G._tooltip + 1] = tostring(text) end
math.atan2 = math.atan2 or function(y, x) return math.atan(y, x) end
SlashCmdList = {}
function CreateFrame(kind, name, parent, template)
  local f = _obj()
  f.kind = kind
  if name then _G[name] = f end
  _G._last_frame = f
  return f
end
function ReloadUI() _G._reloaded = true end
function GetCursorPosition() return 200, 200 end
tinsert = table.insert
UISpecialFrames = {}
ConsolePort = {
  frames = {},
  AddInterfaceCursorFrame = function(self, frame)
    self.frame = frame
    self.frames[#self.frames + 1] = frame
  end,
}
time = os.time
"""


def main() -> int:
    lua = LuaRuntime()
    source = (Path("addon/SofaSay/SofaSay.lua")).read_text(encoding="utf-8")
    lua.execute(PRELUDE)
    lua.execute(source)

    events = lua.eval("_G._last_frame")
    events.scripts["OnEvent"](events, "ADDON_LOADED", "SofaSay")

    failures = 0

    def check(label, condition, detail=""):
        nonlocal failures
        if condition:
            print(f"ok   {label}")
        else:
            failures += 1
            print(f"FAIL {label} {detail}")

    db = lua.eval("SofaSayDB")
    check("defaults created", db["defaultChannel"] == "say" and db["sticky"] is True)
    check("panel hidden at load", lua.eval("SofaSayPanel:IsShown()") is False)
    check("escape closes panel", lua.eval("UISpecialFrames[1]") == "SofaSayPanel")
    check(
        "consoleport pointer registered",
        lua.eval("ConsolePort.frame == SofaSayPanel") is True,
    )
    fonts = lua.eval("_G._fonts")
    texts = [fonts[i].text for i in range(1, len(fonts) + 1) if fonts[i].text]
    check("controller hint in note", any("Controller:" in t for t in texts), texts)

    check("minimap button created", lua.eval("SofaSayMinimapButton ~= nil") is True)
    check("minimap button shown", lua.eval("SofaSayMinimapButton:IsShown()") is True)
    point = lua.eval("SofaSayMinimapButton.point")
    check(
        "minimap positioned bottom-left",
        point is not None and abs(point[4] + 61.28) < 0.5 and abs(point[5] + 51.42) < 0.5,
        point,
    )

    texture = lua.eval("SofaSayMinimapButton.icon.texture")
    check(
        "sofa icon is the default",
        texture is not None and "SofaSay\\sofa" in texture,
        texture,
    )
    lua.eval('SlashCmdList["SOFASAY"]("icon classic")')
    texture = lua.eval("SofaSayMinimapButton.icon.texture")
    check(
        "classic icon fallback",
        texture is not None and "INV_Misc_Spyglass" in texture,
        texture,
    )
    check("icon choice saved", lua.eval("SofaSayDB.icon") == "classic")
    lua.eval('SlashCmdList["SOFASAY"]("icon sofa")')
    texture = lua.eval("SofaSayMinimapButton.icon.texture")
    check(
        "sofa icon restored",
        texture is not None and texture.endswith("sofa"),
        texture,
    )
    lua.eval('SlashCmdList["SOFASAY"]("icon nonsense")')
    check("unknown icon ignored", lua.eval("SofaSayDB.icon") == "sofa")

    lua.eval('SofaSayMinimapButton.scripts.OnClick(SofaSayMinimapButton, "LeftButton")')
    check("minimap click opens panel", lua.eval("SofaSayPanel:IsShown()") is True)
    lua.eval('SofaSayMinimapButton.scripts.OnClick(SofaSayMinimapButton, "LeftButton")')
    check("minimap click closes panel", lua.eval("SofaSayPanel:IsShown()") is False)

    lua.eval('SlashCmdList["SOFASAY"]("status state=running | channel=Party | button=Controller + F9 | mic=Test Mic | last=hello there")')
    check("status stored", lua.eval("SofaSayDB.status").startswith("state=running"))
    check("status time set", lua.eval("SofaSayDB.statusTime") > 0)

    vertex = lua.eval("SofaSayMinimapButton.icon.vertex")
    check(
        "minimap tint running",
        vertex is not None and vertex[2] == 1 and vertex[1] < 0.5,
        vertex,
    )
    lua.eval("SofaSayMinimapButton.scripts.OnEnter(SofaSayMinimapButton)")
    tooltip = [m for m in lua.eval("_G._tooltip").values()]
    check("tooltip shows state", any("Tool: Running" in t for t in tooltip), tooltip)
    check("tooltip shows button", any("Talk button: Controller + F9" in t for t in tooltip), tooltip)
    check("tooltip shows sticky", any("Sticky channel: On" in t for t in tooltip), tooltip)
    check("tooltip reset hint", any("Right-click to reset" in t for t in tooltip), tooltip)

    lua.eval('SlashCmdList["SOFASAY"]("show")')
    check("show opens panel", lua.eval("SofaSayPanel:IsShown()") is True)
    fonts = lua.eval("_G._fonts")
    texts = [fonts[i].text for i in range(1, len(fonts) + 1) if fonts[i].text]
    check("status headline rendered", any("Tool running" in t for t in texts), texts)
    check("channel rendered", any("Channel: Party" in t for t in texts), texts)
    check("last message rendered", any("Last: hello there" in t for t in texts), texts)

    # The age label ticks while the panel stays open.
    lua.execute("SofaSayDB.statusTime = time() - 130")
    lua.eval("SofaSayPanel.scripts.OnUpdate(SofaSayPanel, 20)")
    fonts = lua.eval("_G._fonts")
    texts = [fonts[i].text for i in range(1, len(fonts) + 1) if fonts[i].text]
    check("status age ticks", any(t == "Updated 2m ago" for t in texts), texts)

    lua.eval('SlashCmdList["SOFASAY"]("status state=stopped")')
    fonts = lua.eval("_G._fonts")
    texts = [fonts[i].text for i in range(1, len(fonts) + 1) if fonts[i].text]
    check("stopped headline", any("Tool stopped" in t for t in texts), texts)
    check("stopped age label", any(t == "Stopped just now" for t in texts), texts)
    vertex = lua.eval("SofaSayMinimapButton.icon.vertex")
    check(
        "minimap tint stopped",
        vertex is not None and vertex[1] == 1 and vertex[2] < 0.8,
        vertex,
    )

    lua.eval('SlashCmdList["SOFASAY"]("hide")')
    check("hide closes panel", lua.eval("SofaSayPanel:IsShown()") is False)

    lua.eval('SofaSay_Toggle()')
    check("binding toggles panel", lua.eval("SofaSayPanel:IsShown()") is True)

    lua.eval('SlashCmdList["SOFASAY"]("bogus")')
    check("help printed", any("commands:" in m for m in lua.eval("_G._messages").values()))
    check("help mentions minimap", any("/sofa minimap" in m for m in lua.eval("_G._messages").values()))
    check("help mentions icon", any("/sofa icon" in m for m in lua.eval("_G._messages").values()))
    check("help mentions channel switching", any("/sofa next" in m for m in lua.eval("_G._messages").values()))

    lua.eval('SlashCmdList["SOFASAY"]("minimap off")')
    check("minimap off hides button", lua.eval("SofaSayDB.showMinimap") is False)
    check("minimap off button state", lua.eval("SofaSayMinimapButton:IsShown()") is False)

    lua.eval('SlashCmdList["SOFASAY"]("minimap on")')
    check("minimap on shows button", lua.eval("SofaSayDB.showMinimap") is True)
    check("minimap on button state", lua.eval("SofaSayMinimapButton:IsShown()") is True)

    lua.execute("SofaSayDB.minimapAngle = 10")
    lua.eval('SlashCmdList["SOFASAY"]("minimap reset")')
    check("minimap reset angle", lua.eval("SofaSayDB.minimapAngle") == 220)
    point = lua.eval("SofaSayMinimapButton.point")
    check(
        "minimap reset repositions",
        point is not None and abs(point[4] + 61.28) < 0.5 and abs(point[5] + 51.42) < 0.5,
        point,
    )

    lua.eval("SofaSayMinimapButton.scripts.OnDragStart(SofaSayMinimapButton)")
    lua.eval("SofaSayMinimapButton.scripts.OnUpdate()")
    lua.eval("SofaSayMinimapButton.scripts.OnDragStop(SofaSayMinimapButton)")
    check("drag updates angle", abs(lua.eval("SofaSayDB.minimapAngle") - 45) < 0.1)

    lua.execute("SofaSayDB.minimapAngle = 10")
    lua.eval('SofaSayMinimapButton.scripts.OnClick(SofaSayMinimapButton, "RightButton")')
    check("right-click resets angle", lua.eval("SofaSayDB.minimapAngle") == 220)
    check(
        "right-click does not toggle panel",
        lua.eval("SofaSayPanel:IsShown()") is True,
    )

    lua.eval('SlashCmdList["SOFASAY"]("sticky off")')
    check("sticky command off", lua.eval("SofaSayDB.sticky") is False)
    lua.eval('SlashCmdList["SOFASAY"]("sticky on")')
    check("sticky command on", lua.eval("SofaSayDB.sticky") is True)

    lua.eval('SlashCmdList["SOFASAY"]("escape off")')
    check("escape command off", lua.eval("SofaSayDB.closeChatAfterSend") is False)
    lua.eval('SlashCmdList["SOFASAY"]("escape on")')
    check("escape command on", lua.eval("SofaSayDB.closeChatAfterSend") is True)

    lua.eval('SlashCmdList["SOFASAY"]("channel party")')
    check("channel command", lua.eval("SofaSayDB.defaultChannel") == "party")
    lua.eval('SlashCmdList["SOFASAY"]("channel notachannel")')
    check("unknown channel ignored", lua.eval("SofaSayDB.defaultChannel") == "party")

    lua.eval("SofaSay_CycleChannel(1)")
    check("next channel binding", lua.eval("SofaSayDB.defaultChannel") == "yell")
    lua.eval("SofaSay_CycleChannel(-1)")
    check("previous channel binding", lua.eval("SofaSayDB.defaultChannel") == "party")
    lua.eval('SlashCmdList["SOFASAY"]("next")')
    check("next channel command", lua.eval("SofaSayDB.defaultChannel") == "yell")
    lua.eval('SlashCmdList["SOFASAY"]("prev")')
    check("prev channel command", lua.eval("SofaSayDB.defaultChannel") == "party")

    lua.eval('SlashCmdList["SOFASAY"]("status state=running | channel=Party | button=Controller + F9")')
    lua.eval('SlashCmdList["SOFASAY"]("test")')
    messages = [m for m in lua.eval("_G._messages").values()]
    check("test command answers", any("Test message received" in m for m in messages), messages)
    check("test reports button", any("Button: Controller + F9" in m for m in messages), messages)
    check("help mentions sticky", any("/sofa sticky" in m for m in messages), messages)

    print()
    print(f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
