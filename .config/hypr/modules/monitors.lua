-- modules/monitors.lua

hl.monitor({
output   = "eDP-1",
mode     = "preferred",
position = "0x0",
scale    = "1.0",
})

-- Будущие мониторы.
-- Появятся автоматически при подключении.

hl.monitor({
output   = "HDMI-A-1",
mode     = "preferred",
position = "auto-right",
scale    = "1.0",
})

hl.monitor({
output   = "DP-4",
mode     = "preferred",
position = "auto-right",
scale    = "1.0",
})
