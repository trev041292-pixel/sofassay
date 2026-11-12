-- SofaSay: in-game panel for the SofaSay desktop tool.
--
-- The addon cannot read the tool's config or talk to it directly. It writes
-- its settings to SavedVariables (saved on /reload or logout) and displays
-- status lines the desktop tool types into chat as "/sofa status ...".

local ADDON_NAME = "SofaSay"
local VERSION = "2.1.0"

BINDING_HEADER_SOFASAY = "SofaSay"
BINDING_NAME_TOGGLESOFASAYPANEL = "Toggle SofaSay Panel"
BINDING_NAME_SOFASAYNEXTCHANNEL = "SofaSay: next channel"
BINDING_NAME_SOFASAYPREVCHANNEL = "SofaSay: previous channel"

-- The sofa is bundled with the addon (a grayscale TGA, tinted by the state).
-- The spyglass is the built-in fallback if the custom file will not load.
local ICONS = {
	sofa = "Interface\\AddOns\\" .. ADDON_NAME .. "\\sofa",
	classic = "Interface\\Icons\\INV_Misc_Spyglass_02",
}

local CHANNELS = {
	{ name = "say", label = "Say" },
	{ name = "party", label = "Party" },
	{ name = "yell", label = "Yell" },
	{ name = "guild", label = "Guild" },
	{ name = "officer", label = "Officer" },
	{ name = "raid", label = "Raid" },
	{ name = "raidwarning", label = "Raid Warn" },
	{ name = "instance", label = "Instance" },
	{ name = "general", label = "General" },
	{ name = "trade", label = "Trade" },
	{ name = "localdefense", label = "Defense" },
	{ name = "lfg", label = "LFG" },
	{ name = "worlddefense", label = "World Def" },
	{ name = "reply", label = "Reply" },
	{ name = "emote", label = "Emote" },
}

local DEFAULTS = {
	version = 1,
	defaultChannel = "say",
	sticky = true,
	closeChatAfterSend = true,
	maxChars = 250,
	status = "",
	statusTime = 0,
	x = 0,
	y = 0,
	showMinimap = true,
	minimapAngle = 220,
	icon = "sofa",
}

local panel
local statusText, statusDetail, statusLast, statusAge
local channelButtons = {}
local stickyCheck, closeCheck, minimapCheck, noteText
local minimapButton, minimapIcon
local refreshAll

local function chatPrint(message)
	DEFAULT_CHAT_FRAME:AddMessage("|cff33ff99SofaSay|r " .. tostring(message))
end

local function initDB()
	SofaSayDB = SofaSayDB or {}
	for key, value in pairs(DEFAULTS) do
		if SofaSayDB[key] == nil then
			SofaSayDB[key] = value
		end
	end
	SofaSayDB.version = DEFAULTS.version
end

local function labelFor(name)
	for _, channel in ipairs(CHANNELS) do
		if channel.name == name then
			return channel.label
		end
	end
	return name
end

local function channelByName(value)
	local wanted = string.lower(string.gsub(value or "", "%s+", ""))
	if wanted == "" then
		return nil
	end
	for _, channel in ipairs(CHANNELS) do
		local label = string.lower(string.gsub(channel.label, "%s+", ""))
		if channel.name == wanted or label == wanted then
			return channel.name, channel.label
		end
	end
	return nil
end

local function parseOnOff(value)
	value = string.lower(value or "")
	if value == "on" or value == "true" or value == "1" then
		return true
	end
	if value == "off" or value == "false" or value == "0" then
		return false
	end
	return nil
end

local function statusFields(text)
	local fields = {}
	if not text or text == "" then
		return fields
	end
	for part in string.gmatch(text, "[^|]+") do
		local key, value = string.match(part, "^%s*([%w_]+)%s*=%s*(.-)%s*$")
		if key then
			fields[string.lower(key)] = value
		end
	end
	return fields
end

-- Swap between the bundled sofa and the built-in spyglass.
local function applyMinimapIcon()
	if not minimapIcon then
		return
	end
	local texture = ICONS[string.lower(SofaSayDB.icon or "sofa")] or ICONS.sofa
	minimapIcon:SetTexture(texture)
end

-- Tint the minimap icon so the state is visible without opening anything.
local function updateMinimapState()
	if not minimapIcon then
		return
	end
	local state = statusFields(SofaSayDB.status or "").state
	if state == "running" then
		minimapIcon:SetVertexColor(0.35, 1, 0.35)
	elseif state == "stopped" then
		minimapIcon:SetVertexColor(1, 0.75, 0.25)
	else
		minimapIcon:SetVertexColor(0.65, 0.65, 0.65)
	end
end

local function ageText(seconds)
	if seconds < 60 then
		return "just now"
	elseif seconds < 3600 then
		return math.floor(seconds / 60) .. "m ago"
	elseif seconds < 86400 then
		return math.floor(seconds / 3600) .. "h ago"
	end
	return math.floor(seconds / 86400) .. "d ago"
end

local function updateStatusAge()
	if not statusAge then
		return
	end
	if not (SofaSayDB.statusTime and SofaSayDB.statusTime > 0) then
		statusAge:SetText("No status yet")
		return
	end
	local age = time() - SofaSayDB.statusTime
	if age < 0 then
		age = 0
	end
	local state = statusFields(SofaSayDB.status or "").state
	if state == "stopped" then
		statusAge:SetText("Stopped " .. ageText(age))
	else
		statusAge:SetText("Updated " .. ageText(age))
	end
end

local function setNote(text)
	if noteText then
		noteText:SetText(text or "")
	end
end

-- ConsolePort (if installed) gives the panel a virtual pointer, so a controller
-- can click the buttons. The addon still works without it.
local function consolePortAvailable()
	local cp = _G.ConsolePort
	return cp and cp.AddInterfaceCursorFrame and true or false
end

local function registerWithConsolePort()
	if not panel then
		return
	end
	local cp = _G.ConsolePort
	if not (cp and cp.AddInterfaceCursorFrame) then
		return
	end
	pcall(cp.AddInterfaceCursorFrame, cp, panel)
end

local function defaultNote()
	if consolePortAvailable() then
		return "Controller: move the pointer with the stick and press A to click. B or Escape closes this panel. Changes save with Save & Reload UI."
	end
	return "Changes are written when you click Save & Reload UI (or log out). The desktop tool applies them within a few seconds."
end

local function refreshChannels()
	for index, channel in ipairs(CHANNELS) do
		local button = channelButtons[index]
		if button then
			if channel.name == SofaSayDB.defaultChannel then
				button:SetText("|cff40ff40" .. channel.label .. "|r")
			else
				button:SetText(channel.label)
			end
		end
	end
end

local function refreshStatus()
	if not statusText then
		return
	end

	local raw = SofaSayDB.status or ""
	local fields = statusFields(raw)
	local headline, color

	if fields.state == "running" then
		headline, color = "Tool running", "|cff40ff40"
	elseif fields.state == "stopped" then
		headline, color = "Tool stopped", "|cffffcc33"
	elseif raw ~= "" then
		headline, color = raw, "|cffffffff"
	else
		headline, color = "Waiting for the desktop tool", "|cffaaaaaa"
	end

	statusText:SetText(color .. headline .. "|r")

	local details = {}
	if fields.channel then
		details[#details + 1] = "Channel: " .. fields.channel
	end
	if fields.mic then
		details[#details + 1] = "Mic: " .. fields.mic
	end
	if #details == 0 and raw ~= "" and headline ~= raw then
		details[1] = raw
	end
	statusDetail:SetText(table.concat(details, "   |cff666666|r   "))

	local last = fields.last or fields.model
	if last then
		statusLast:SetText("Last: " .. last)
	else
		statusLast:SetText("")
	end

	updateStatusAge()
	updateMinimapState()
end

refreshAll = function()
	refreshChannels()
	refreshStatus()
	if stickyCheck then
		stickyCheck:SetChecked(SofaSayDB.sticky and true or false)
	end
	if closeCheck then
		closeCheck:SetChecked(SofaSayDB.closeChatAfterSend and true or false)
	end
	if minimapCheck then
		minimapCheck:SetChecked(SofaSayDB.showMinimap and true or false)
	end
end

local function setChannel(name)
	if SofaSayDB.defaultChannel == name then
		setNote("Already selected. Click Save & Reload UI to make sure the tool has it.")
		return
	end
	SofaSayDB.defaultChannel = name
	refreshChannels()
	setNote("Selected " .. labelFor(name) .. ". Click Save & Reload UI so the desktop tool applies it.")
end

-- Used by the next/previous channel key bindings (bindable to controller
-- buttons in ConsolePort) so a controller player can switch channels without
-- opening the panel.
function SofaSay_CycleChannel(step)
	initDB()
	step = tonumber(step) or 1
	local count = #CHANNELS
	local index = 1
	for i, channel in ipairs(CHANNELS) do
		if channel.name == SofaSayDB.defaultChannel then
			index = i
			break
		end
	end
	index = ((index - 1 + step) % count) + 1
	local channel = CHANNELS[index]
	SofaSayDB.defaultChannel = channel.name
	refreshChannels()
	setNote("Selected " .. channel.label .. ". Click Save & Reload UI so the desktop tool applies it.")
	chatPrint("Channel: " .. channel.label .. ". Saved on /reload or logout.")
end

local function makeButton(parent, text, width, height, onClick)
	local button = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
	button:SetSize(width, height)
	button:SetText(text)
	button:SetScript("OnClick", onClick)
	return button
end

-- ---------------------------------------------------------------------------
-- Minimap button
-- ---------------------------------------------------------------------------
local function updateMinimapPosition()
	if not minimapButton or not Minimap then
		return
	end
	local angle = math.rad(SofaSayDB.minimapAngle or 220)
	local width = Minimap:GetWidth() or 140
	local radius = width / 2 + 10
	minimapButton:ClearAllPoints()
	minimapButton:SetPoint(
		"CENTER",
		Minimap,
		"CENTER",
		math.cos(angle) * radius,
		math.sin(angle) * radius
	)
end

local function updateMinimapVisibility()
	if not minimapButton then
		return
	end
	if SofaSayDB.showMinimap == false then
		minimapButton:Hide()
	else
		minimapButton:Show()
	end
end

local function buildMinimapButton()
	if minimapButton then
		updateMinimapVisibility()
		return
	end
	if not Minimap then
		return
	end

	minimapButton = CreateFrame("Button", "SofaSayMinimapButton", Minimap)
	minimapButton:SetSize(32, 32)
	minimapButton:SetFrameStrata("MEDIUM")
	minimapButton:SetFrameLevel((Minimap:GetFrameLevel() or 1) + 8)
	minimapButton:RegisterForDrag("LeftButton")
	minimapButton:SetMovable(true)

	local background = minimapButton:CreateTexture(nil, "BACKGROUND")
	background:SetTexture("Interface\\Minimap\\UI-Minimap-Background")
	background:SetSize(20, 20)
	background:SetPoint("CENTER")

	local icon = minimapButton:CreateTexture(nil, "ARTWORK")
	icon:SetTexture(ICONS.sofa)
	icon:SetSize(20, 20)
	icon:SetPoint("CENTER")
	icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
	minimapIcon = icon
	minimapButton.icon = icon
	applyMinimapIcon()

	local border = minimapButton:CreateTexture(nil, "OVERLAY")
	border:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
	border:SetSize(54, 54)
	border:SetPoint("TOPLEFT")

	minimapButton:SetScript("OnClick", function(_, button)
		if button == "RightButton" then
			SofaSayDB.minimapAngle = 220
			updateMinimapPosition()
			chatPrint("Minimap button moved back to its default position.")
			return
		end
		SofaSay_Toggle()
	end)

	minimapButton:SetScript("OnEnter", function(self)
		GameTooltip:SetOwner(self, "ANCHOR_LEFT")
		GameTooltip:AddLine("SofaSay")
		GameTooltip:AddLine("Click to open settings (the controller pointer works too)", 1, 1, 1)
		GameTooltip:AddLine("Drag to move around the minimap", 0.7, 0.7, 0.7)
		GameTooltip:AddLine("Right-click to reset the position", 0.7, 0.7, 0.7)
		local fields = statusFields(SofaSayDB.status or "")
		if fields.state == "running" then
			GameTooltip:AddLine("Tool: Running", 0.35, 1, 0.35)
		elseif fields.state == "stopped" then
			GameTooltip:AddLine("Tool: Stopped", 1, 0.75, 0.25)
		else
			GameTooltip:AddLine("Tool: waiting for a status", 0.7, 0.7, 0.7)
		end
		if fields.button then
			GameTooltip:AddLine("Talk button: " .. fields.button, 1, 1, 1)
		end
		GameTooltip:AddLine("Channel: " .. labelFor(SofaSayDB.defaultChannel), 0.5, 1, 0.5)
		GameTooltip:AddLine("Sticky channel: " .. (SofaSayDB.sticky and "On" or "Off"), 0.8, 0.8, 0.8)
		GameTooltip:Show()
	end)
	minimapButton:SetScript("OnLeave", function()
		GameTooltip:Hide()
	end)

	local function moveMinimapButton()
		if not Minimap then
			return
		end
		local cx, cy = Minimap:GetCenter()
		local scale = Minimap:GetEffectiveScale()
		local x, y = GetCursorPosition()
		if not (cx and cy and scale and scale > 0 and x and y) then
			return
		end
		SofaSayDB.minimapAngle = math.deg(math.atan2(y / scale - cy, x / scale - cx))
		updateMinimapPosition()
	end

	minimapButton:SetScript("OnDragStart", function(self)
		self:SetScript("OnUpdate", moveMinimapButton)
	end)
	minimapButton:SetScript("OnDragStop", function(self)
		self:SetScript("OnUpdate", nil)
	end)

	updateMinimapPosition()
	updateMinimapVisibility()
	updateMinimapState()
end

local function buildPanel()
	if panel then
		return
	end

	panel = CreateFrame("Frame", "SofaSayPanel", UIParent, "BackdropTemplate")
	panel:SetSize(400, 500)
	panel:SetPoint("CENTER", UIParent, "CENTER", SofaSayDB.x or 0, SofaSayDB.y or 0)
	panel:SetFrameStrata("DIALOG")
	panel:SetToplevel(true)
	panel:SetClampedToScreen(true)
	panel:SetMovable(true)
	panel:EnableMouse(true)
	-- Escape closes the panel. ConsolePort maps B to Escape, so B works too.
	if UISpecialFrames then
		tinsert(UISpecialFrames, "SofaSayPanel")
	end
	panel:RegisterForDrag("LeftButton")
	panel:SetScript("OnDragStart", panel.StartMoving)
	panel:SetScript("OnDragStop", function(self)
		self:StopMovingOrSizing()
		local x, y = self:GetCenter()
		local ux, uy = UIParent:GetCenter()
		if x and y and ux and uy then
			SofaSayDB.x = math.floor(x - ux + 0.5)
			SofaSayDB.y = math.floor(y - uy + 0.5)
		end
	end)
	panel:SetBackdrop({
		bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
		edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
		tile = true,
		tileSize = 32,
		edgeSize = 32,
		insets = { left = 11, right = 12, top = 12, bottom = 11 },
	})

	local title = panel:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
	title:SetPoint("TOPLEFT", 18, -16)
	title:SetText("SofaSay")

	local close = CreateFrame("Button", nil, panel, "UIPanelCloseButton")
	close:SetPoint("TOPRIGHT", -5, -5)

	local statusBg = CreateFrame("Frame", nil, panel, "BackdropTemplate")
	statusBg:SetPoint("TOPLEFT", 16, -42)
	statusBg:SetSize(368, 96)
	statusBg:SetBackdrop({
		bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
		edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
		tile = true,
		tileSize = 16,
		edgeSize = 12,
		insets = { left = 3, right = 3, top = 3, bottom = 3 },
	})
	statusBg:SetBackdropColor(0, 0, 0, 0.6)
	statusBg:SetBackdropBorderColor(1, 1, 1, 0.15)

	statusText = statusBg:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
	statusText:SetPoint("TOPLEFT", 12, -10)
	statusText:SetPoint("TOPRIGHT", -12, -10)
	statusText:SetJustifyH("LEFT")

	statusDetail = statusBg:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
	statusDetail:SetPoint("TOPLEFT", 12, -36)
	statusDetail:SetPoint("TOPRIGHT", -12, -36)
	statusDetail:SetJustifyH("LEFT")

	statusLast = statusBg:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
	statusLast:SetPoint("TOPLEFT", 12, -56)
	statusLast:SetPoint("TOPRIGHT", -12, -56)
	statusLast:SetJustifyH("LEFT")
	statusLast:SetTextColor(0.8, 0.8, 0.8)

	statusAge = statusBg:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
	statusAge:SetPoint("BOTTOMRIGHT", -12, 8)

	local channelLabel = panel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
	channelLabel:SetPoint("TOPLEFT", 18, -150)
	channelLabel:SetText("Channel for the next message")

	local grid = CreateFrame("Frame", nil, panel)
	grid:SetPoint("TOPLEFT", 16, -170)
	grid:SetSize(368, 136)

	local columns, buttonWidth, buttonHeight, gap = 4, 86, 28, 8
	for index, channel in ipairs(CHANNELS) do
		local column = (index - 1) % columns
		local row = math.floor((index - 1) / columns)
		local button = makeButton(grid, channel.label, buttonWidth, buttonHeight, function()
			setChannel(channel.name)
		end)
		button:SetPoint("TOPLEFT", column * (buttonWidth + gap), -row * (buttonHeight + gap))
		button:SetScript("OnEnter", function(self)
			GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
			GameTooltip:SetText(channel.label .. " chat", 1, 1, 1)
			GameTooltip:AddLine("Sets the default channel used by the voice tool.", 1, 1, 1, true)
			GameTooltip:Show()
		end)
		button:SetScript("OnLeave", function()
			GameTooltip:Hide()
		end)
		channelButtons[index] = button
	end

	noteText = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
	noteText:SetPoint("TOPLEFT", 18, -314)
	noteText:SetWidth(364)
	noteText:SetJustifyH("LEFT")
	noteText:SetTextColor(0.85, 0.85, 0.85)
	noteText:SetText(defaultNote())

	stickyCheck = CreateFrame("CheckButton", nil, panel, "UICheckButtonTemplate")
	stickyCheck:SetPoint("TOPLEFT", 16, -364)
	stickyCheck:SetScript("OnClick", function(self)
		SofaSayDB.sticky = self:GetChecked() and true or false
		setNote("Sticky channel " .. (SofaSayDB.sticky and "enabled" or "disabled") .. ". Click Save & Reload UI to apply.")
	end)
	local stickyLabel = panel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
	stickyLabel:SetPoint("LEFT", stickyCheck, "RIGHT", 2, 0)
	stickyLabel:SetText("Remember the last channel")

	closeCheck = CreateFrame("CheckButton", nil, panel, "UICheckButtonTemplate")
	closeCheck:SetPoint("TOPLEFT", 16, -394)
	closeCheck:SetScript("OnClick", function(self)
		SofaSayDB.closeChatAfterSend = self:GetChecked() and true or false
		setNote("Escape-after-send " .. (SofaSayDB.closeChatAfterSend and "enabled" or "disabled") .. ". Click Save & Reload UI to apply.")
	end)
	local closeLabel = panel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
	closeLabel:SetPoint("LEFT", closeCheck, "RIGHT", 2, 0)
	closeLabel:SetText("Press Escape after sending")

	minimapCheck = CreateFrame("CheckButton", nil, panel, "UICheckButtonTemplate")
	minimapCheck:SetPoint("TOPLEFT", 16, -424)
	minimapCheck:SetScript("OnClick", function(self)
		SofaSayDB.showMinimap = self:GetChecked() and true or false
		updateMinimapVisibility()
		setNote("Minimap button " .. (SofaSayDB.showMinimap and "shown" or "hidden") .. ". This applies immediately and is saved on /reload or logout.")
	end)
	local minimapLabel = panel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
	minimapLabel:SetPoint("LEFT", minimapCheck, "RIGHT", 2, 0)
	minimapLabel:SetText("Show minimap button")

	local hint = panel:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
	hint:SetPoint("BOTTOMLEFT", 18, 20)
	hint:SetText("/sofa  |  SofaSay " .. VERSION)

	local reloadButton = makeButton(panel, "Save & Reload UI", 150, 22, function()
		ReloadUI()
	end)
	reloadButton:SetPoint("BOTTOMRIGHT", -18, 16)

	local hideButton = makeButton(panel, "Close", 80, 22, function()
		panel:Hide()
	end)
	hideButton:SetPoint("RIGHT", reloadButton, "LEFT", -6, 0)

	panel:SetScript("OnShow", function()
		refreshAll()
		setNote(defaultNote())
	end)

	-- Keep "Updated 5m ago" honest while the panel is open. The tool sends a
	-- fresh status when it starts, stops, or (optionally) after a message.
	local ageSeconds = 0
	panel:SetScript("OnUpdate", function(_, elapsed)
		ageSeconds = ageSeconds + (elapsed or 0)
		if ageSeconds < 15 then
			return
		end
		ageSeconds = 0
		updateStatusAge()
	end)

	refreshAll()
	panel:Hide()
	registerWithConsolePort()
end

local function showPanel()
	buildPanel()
	refreshAll()
	panel:Show()
end

function SofaSay_Toggle()
	if panel and panel:IsShown() then
		panel:Hide()
	else
		showPanel()
	end
end

local function setStatus(text)
	SofaSayDB.status = text or ""
	SofaSayDB.statusTime = time()
	if panel and panel:IsShown() then
		refreshStatus()
	end
	updateMinimapState()
	if text and text ~= "" then
		chatPrint("Status updated.")
	end
end

local function printHelp()
	chatPrint("commands:")
	chatPrint("  /sofa - show or hide the panel")
	chatPrint("  /sofa show | hide | toggle - panel visibility")
	chatPrint("  /sofa minimap [on|off|reset] - show, hide, or move the minimap button")
	chatPrint("  /sofa icon [sofa|classic] - minimap button art")
	chatPrint("  /sofa channel <name> - choose the default channel")
	chatPrint("  /sofa next | prev - switch to the next or previous channel")
	chatPrint("  /sofa sticky [on|off] - remember the last channel")
	chatPrint("  /sofa escape [on|off] - press Escape after sending")
	chatPrint("  /sofa test - check that the desktop tool can type here")
	chatPrint("  /sofa status <text> - used by the desktop tool")
	chatPrint("  /sofa reload - save settings and reload the UI")
end

SLASH_SOFASAY1 = "/sofa"
SLASH_SOFASAY2 = "/sofassay"
SlashCmdList["SOFASAY"] = function(msg)
	initDB()
	local command, rest = string.match(msg or "", "^%s*(%S*)%s*(.-)%s*$")
	command = string.lower(command or "")
	rest = rest or ""

	if command == "" or command == "toggle" then
		SofaSay_Toggle()
	elseif command == "show" then
		showPanel()
	elseif command == "hide" then
		if panel then
			panel:Hide()
		end
	elseif command == "minimap" then
		buildMinimapButton()
		local value = string.lower(rest)
		if value == "reset" then
			SofaSayDB.minimapAngle = 220
			updateMinimapPosition()
			chatPrint("Minimap button moved back to its default position.")
		else
			if value == "on" then
				SofaSayDB.showMinimap = true
			elseif value == "off" then
				SofaSayDB.showMinimap = false
			else
				SofaSayDB.showMinimap = not SofaSayDB.showMinimap
			end
			updateMinimapVisibility()
			if minimapCheck then
				minimapCheck:SetChecked(SofaSayDB.showMinimap and true or false)
			end
			chatPrint("Minimap button " .. (SofaSayDB.showMinimap and "shown" or "hidden") .. ".")
		end
	elseif command == "status" then
		setStatus(rest)
	elseif command == "icon" then
		local value = string.lower(rest)
		if value == "" then
			value = (SofaSayDB.icon == "classic") and "sofa" or "classic"
		end
		if value ~= "sofa" and value ~= "classic" then
			chatPrint("Unknown icon \"" .. rest .. "\". Use sofa or classic.")
		else
			SofaSayDB.icon = value
			applyMinimapIcon()
			chatPrint("Minimap icon set to " .. value .. ".")
		end
	elseif command == "channel" then
		local name, label = channelByName(rest)
		if not name then
			chatPrint("Unknown channel \"" .. rest .. "\". Try /sofa to see the list.")
		else
			buildPanel()
			setChannel(name)
			chatPrint("Channel set to " .. label .. ".")
		end
	elseif command == "next" then
		SofaSay_CycleChannel(1)
	elseif command == "prev" or command == "previous" then
		SofaSay_CycleChannel(-1)
	elseif command == "sticky" then
		local value = parseOnOff(rest)
		if value == nil then
			value = not SofaSayDB.sticky
		end
		SofaSayDB.sticky = value
		if stickyCheck then
			stickyCheck:SetChecked(value)
		end
		setNote("Sticky channel " .. (value and "enabled" or "disabled") .. ". Click Save & Reload UI to apply.")
		chatPrint("Sticky channel " .. (value and "on" or "off") .. ".")
	elseif command == "escape" then
		local value = parseOnOff(rest)
		if value == nil then
			value = not SofaSayDB.closeChatAfterSend
		end
		SofaSayDB.closeChatAfterSend = value
		if closeCheck then
			closeCheck:SetChecked(value)
		end
		setNote("Escape-after-send " .. (value and "enabled" or "disabled") .. ". Click Save & Reload UI to apply.")
		chatPrint("Escape after sending " .. (value and "on" or "off") .. ".")
	elseif command == "test" then
		local fields = statusFields(SofaSayDB.status or "")
		chatPrint("Test message received. The desktop tool can type into chat.")
		local extra = "State: " .. (fields.state or "unknown")
		if fields.button then
			extra = extra .. "   Button: " .. fields.button
		end
		chatPrint(extra)
	elseif command == "reload" then
		ReloadUI()
	else
		printHelp()
	end
end

local events = CreateFrame("Frame")
events:RegisterEvent("ADDON_LOADED")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function(_, event, name)
	if event == "ADDON_LOADED" and name == ADDON_NAME then
		initDB()
		buildPanel()
		buildMinimapButton()
		registerWithConsolePort()
		if SofaSayDB.status ~= "" then
			chatPrint("Loaded. Type /sofa to open the panel.")
		end
	elseif event == "PLAYER_LOGIN" or (event == "ADDON_LOADED" and name == "ConsolePort") then
		-- Covers a load order where ConsolePort finishes after SofaSay.
		registerWithConsolePort()
	end
end)
