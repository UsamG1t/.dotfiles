-- modules/rules.lua

-- Firefox, Telegram, Thunderbird и мессенджеры → Social

hl.window_rule({
name  = "firefox-to-social",
match = { class = "firefox" },
workspace = workspaces.social,
})

hl.window_rule({
name  = "telegram-to-social",
match = { class = "org.telegram.desktop" },
workspace = workspaces.social,
})

hl.window_rule({
name  = "thunderbird-to-social",
match = { class = "thunderbird" },
workspace = workspaces.social,
})

-- IDE и графические редакторы кода → Code

hl.window_rule({
name  = "vscode-to-code",
match = { class = "code-oss" },
workspace = workspaces.code,
})

hl.window_rule({
name  = "subl-to-code",
match = { class = "sublime_text" },
workspace = workspaces.code,
})

hl.window_rule({
name  = "kate-to-code",
match = { class = "org.kde.kate" },
workspace = workspaces.code,
})

-- Виртуализация → Virtual

hl.window_rule({
name  = "virtualbox-to-virtual",
match = { class = "VirtualBox Manager" },
workspace = workspaces.virtual,
})

hl.window_rule({
name  = "virt-manager-to-virtual",
match = { class = "virt-manager" },
workspace = workspaces.virtual,
})

-- Терминальный файловый менеджер → Terminal

hl.window_rule({
name  = "yazi-to-terminal",
match = { class = "kitty-yazi" },
workspace = workspaces.terminal,
})

hl.window_rule({
name  = "kitty-terminal-to-terminal",
match = {class = "kitty-terminal"},
workspace = workspaces.terminal,
})

-- btop как плавающее окно

hl.window_rule({
name  = "btop-floating",
match = { class = "kitty-btop" },
float = true,
size  = "80% 80%",
center = true,
})

hl.window_rule({
name  = "calendar-popup",
match = { class = "calendar-popup" },
float = true,
size  = "250 300",
move  = "835 35",
})
 
-- Попап управления сетью (клик по network в waybar)
 
hl.window_rule({
name   = "nmtui-popup",
match  = { class = "nmtui-popup" },
float  = true,
center = true,
})

-- Попап Bluetooth (клик по bluetooth в waybar)

hl.window_rule({
    name   = "bluetooth-popup",
    match  = { class = "bluetooth-popup" },
    float  = true,
    center = true,
})

-- Всплывающая подсказка по кейбиндам (Super+Shift+/)

hl.window_rule({
name    = "keyhint-popup",
match   = { class = "keyhint" },
float   = true,
size    = "512 360", -- TODO: autosetting
move    = "740 180", -- TODO: autosetting
opacity = "0.5 0.5",    -- active inactive; откалибруй под себя
})

