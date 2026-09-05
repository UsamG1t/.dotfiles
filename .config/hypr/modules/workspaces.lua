-- modules/workspaces.lua

local LAPTOP = "eDP-1"

-- Основные рабочие столы ноутбука
hl.workspace_rule({
workspace = "1",
monitor   = LAPTOP,
default   = true,
})

hl.workspace_rule({
workspace = "2",
monitor   = LAPTOP,
})

hl.workspace_rule({
workspace = "3",
monitor   = LAPTOP,
})

hl.workspace_rule({
workspace = "4",
monitor   = LAPTOP,
})

hl.workspace_rule({
workspace = "5",
monitor   = LAPTOP,
})

hl.workspace_rule({
workspace = "6",
monitor   = LAPTOP,
})

hl.workspace_rule({
workspace = "7",
monitor   = LAPTOP,
})

-- Внешние мониторы
hl.workspace_rule({
workspace = "8",
monitor   = "HDMI-A-1",
})

hl.workspace_rule({
workspace = "9",
monitor   = "DP-4",
})
