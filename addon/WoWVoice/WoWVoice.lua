-- WoWVoice: in-game panel for the WoW Voice Chat desktop tool.
--
-- The addon cannot read the tool's config or talk to it directly. It writes
-- its settings to SavedVariables (saved on /reload or logout) and displays
-- status lines the desktop tool types into chat as "/wvc status ...".

local ADDON_NAME = "WoWVoice"
local VERSION = "1.0.0"

BINDING_HEADER_WOWVOICE = "WoW Voice Chat"
BINDING_NAME_TOGGLEWOWVOICEPANEL = "Toggle WoWVoice Panel"

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
}

local panel
local statusText, statusDetail, statusLast, statusAge
local channelButtons = {}
local stickyCheck, closeCheck, noteText
local refreshAll

local function chatPrint(message)
	DEFAULT_CHAT_FRAME:AddMessage("|cff33ff99WoWVoice|r " .. tostring(message))
end

local function initDB()
	WoWVoiceDB = WoWVoiceDB or {}
	for key, value in pairs(DEFAULTS) do
		if WoWVoiceDB[key] == nil then
			WoWVoiceDB[key] = value
		end
	end
	WoWVoiceDB.version = DEFAULTS.version
end

local function labelFor(name)
	for _, channel in ipairs(CHANNELS) do
		if channel.name == name then
			return channel.label
		end
	end
	return name
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

local function setNote(text)
	if noteText then
		noteText:SetText(text or "")
	end
end

local function refreshChannels()
	for index, channel in ipairs(CHANNELS) do
		local button = channelButtons[index]
		if button then
			if channel.name == WoWVoiceDB.defaultChannel then
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

	local raw = WoWVoiceDB.status or ""
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

	if WoWVoiceDB.statusTime and WoWVoiceDB.statusTime > 0 then
		local age = time() - WoWVoiceDB.statusTime
		if age < 0 then
			age = 0
		end
		statusAge:SetText("Updated " .. ageText(age))
	else
		statusAge:SetText("No status yet")
	end
end

refreshAll = function()
	refreshChannels()
	refreshStatus()
	if stickyCheck then
		stickyCheck:SetChecked(WoWVoiceDB.sticky and true or false)
	end
	if closeCheck then
		closeCheck:SetChecked(WoWVoiceDB.closeChatAfterSend and true or false)
	end
end

local function setChannel(name)
	if WoWVoiceDB.defaultChannel == name then
		setNote("Already selected. Click Save & Reload UI to make sure the tool has it.")
		return
	end
	WoWVoiceDB.defaultChannel = name
	refreshChannels()
	setNote("Selected " .. labelFor(name) .. ". Click Save & Reload UI so the desktop tool applies it.")
end

local function makeButton(parent, text, width, height, onClick)
	local button = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
	button:SetSize(width, height)
	button:SetText(text)
	button:SetScript("OnClick", onClick)
	return button
end

local function buildPanel()
	if panel then
		return
	end

	panel = CreateFrame("Frame", "WoWVoicePanel", UIParent, "BackdropTemplate")
	panel:SetSize(400, 470)
	panel:SetPoint("CENTER", UIParent, "CENTER", WoWVoiceDB.x or 0, WoWVoiceDB.y or 0)
	panel:SetFrameStrata("DIALOG")
	panel:SetToplevel(true)
	panel:SetClampedToScreen(true)
	panel:SetMovable(true)
	panel:EnableMouse(true)
	panel:RegisterForDrag("LeftButton")
	panel:SetScript("OnDragStart", panel.StartMoving)
	panel:SetScript("OnDragStop", function(self)
		self:StopMovingOrSizing()
		local x, y = self:GetCenter()
		local ux, uy = UIParent:GetCenter()
		if x and y and ux and uy then
			WoWVoiceDB.x = math.floor(x - ux + 0.5)
			WoWVoiceDB.y = math.floor(y - uy + 0.5)
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
	title:SetText("WoW Voice Chat")

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
	grid:SetSize(368, 106)

	local columns, buttonWidth, buttonHeight, gap = 4, 86, 22, 6
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
	noteText:SetPoint("TOPLEFT", 18, -284)
	noteText:SetWidth(364)
	noteText:SetJustifyH("LEFT")
	noteText:SetTextColor(0.85, 0.85, 0.85)
	noteText:SetText("Changes are written when you click Save & Reload UI (or log out). The desktop tool applies them within a few seconds.")

	stickyCheck = CreateFrame("CheckButton", nil, panel, "UICheckButtonTemplate")
	stickyCheck:SetPoint("TOPLEFT", 16, -334)
	stickyCheck:SetScript("OnClick", function(self)
		WoWVoiceDB.sticky = self:GetChecked() and true or false
		setNote("Sticky channel " .. (WoWVoiceDB.sticky and "enabled" or "disabled") .. ". Click Save & Reload UI to apply.")
	end)
	local stickyLabel = panel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
	stickyLabel:SetPoint("LEFT", stickyCheck, "RIGHT", 2, 0)
	stickyLabel:SetText("Remember the last channel")

	closeCheck = CreateFrame("CheckButton", nil, panel, "UICheckButtonTemplate")
	closeCheck:SetPoint("TOPLEFT", 16, -364)
	closeCheck:SetScript("OnClick", function(self)
		WoWVoiceDB.closeChatAfterSend = self:GetChecked() and true or false
		setNote("Escape-after-send " .. (WoWVoiceDB.closeChatAfterSend and "enabled" or "disabled") .. ". Click Save & Reload UI to apply.")
	end)
	local closeLabel = panel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
	closeLabel:SetPoint("LEFT", closeCheck, "RIGHT", 2, 0)
	closeLabel:SetText("Press Escape after sending")

	local hint = panel:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
	hint:SetPoint("BOTTOMLEFT", 18, 20)
	hint:SetText("/wvc  |  WoWVoice " .. VERSION)

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
	end)

	refreshAll()
	panel:Hide()
end

local function showPanel()
	buildPanel()
	refreshAll()
	panel:Show()
end

function WoWVoice_Toggle()
	if panel and panel:IsShown() then
		panel:Hide()
	else
		showPanel()
	end
end

local function setStatus(text)
	WoWVoiceDB.status = text or ""
	WoWVoiceDB.statusTime = time()
	if panel and panel:IsShown() then
		refreshStatus()
	end
	if text and text ~= "" then
		chatPrint("Status updated.")
	end
end

local function printHelp()
	chatPrint("commands:")
	chatPrint("  /wvc - show or hide the panel")
	chatPrint("  /wvc show | hide | toggle - panel visibility")
	chatPrint("  /wvc status <text> - used by the desktop tool")
	chatPrint("  /wvc reload - save settings and reload the UI")
end

SLASH_WOWVOICE1 = "/wvc"
SLASH_WOWVOICE2 = "/wowvoice"
SlashCmdList["WOWVOICE"] = function(msg)
	initDB()
	local command, rest = string.match(msg or "", "^%s*(%S*)%s*(.-)%s*$")
	command = string.lower(command or "")
	rest = rest or ""

	if command == "" or command == "toggle" then
		WoWVoice_Toggle()
	elseif command == "show" then
		showPanel()
	elseif command == "hide" then
		if panel then
			panel:Hide()
		end
	elseif command == "status" then
		setStatus(rest)
	elseif command == "reload" then
		ReloadUI()
	else
		printHelp()
	end
end

local events = CreateFrame("Frame")
events:RegisterEvent("ADDON_LOADED")
events:SetScript("OnEvent", function(_, _, name)
	if name ~= ADDON_NAME then
		return
	end
	initDB()
	buildPanel()
	if WoWVoiceDB.status ~= "" then
		chatPrint("Loaded. Type /wvc to open the panel.")
	end
end)
