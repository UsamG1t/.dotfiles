-- modules/keybinds.lua

local mainMod = "SUPER"

-- Applications
hl.bind(mainMod .. " + Q",              hl.dsp.exec_cmd(apps.terminal_ws))    -- Terminal → workspace
hl.bind(mainMod .. " + CTRL + Q",       hl.dsp.exec_cmd(apps.terminal))       -- Terminal → here
hl.bind(mainMod .. " + E",              hl.dsp.exec_cmd(apps.yazi))            -- File manager → workspace
hl.bind(mainMod .. " + CTRL + E",       hl.dsp.exec_cmd(apps.yazi_local))     -- File manager → here
hl.bind(mainMod .. " + F",              hl.dsp.exec_cmd(apps.browser))         -- Browser → workspace
hl.bind(mainMod .. " + CTRL + F",       hl.dsp.exec_cmd("firefox-here"))       -- Browser → here
hl.bind(mainMod .. " + bracketright",            hl.dsp.exec_cmd(apps.editor))        -- Editor → workspace
hl.bind(mainMod .. " + CTRL + bracketright",     hl.dsp.exec_cmd(apps.editor_local))  -- Editor → here
hl.bind(mainMod .. " + bracketleft",            hl.dsp.exec_cmd(apps.texter))        -- Sublime → workspace
hl.bind(mainMod .. " + CTRL + bracketleft",     hl.dsp.exec_cmd(apps.texter_local))  -- Sublime → here
hl.bind(mainMod .. " + R",              hl.dsp.exec_cmd(apps.menu))            -- App launcher
hl.bind(mainMod .. " + CTRL + I",       hl.dsp.exec_cmd("toggle-btop"))        -- Toggle system monitor

-- Other workspace
hl.bind(mainMod .. " + O",         hl.dsp.focus({ workspace = workspaces.other }))   -- Focus other workspace
hl.bind(mainMod .. " + SHIFT + O", hl.dsp.exec_cmd("send-home-or-other"))            -- Toggle: Other ↔ home workspace

-- Vim-like focus
hl.bind(mainMod .. " + H", hl.dsp.focus({ direction = "left" }))   -- Focus left
hl.bind(mainMod .. " + J", hl.dsp.focus({ direction = "down" }))   -- Focus down
hl.bind(mainMod .. " + K", hl.dsp.focus({ direction = "up" }))     -- Focus up
hl.bind(mainMod .. " + L", hl.dsp.focus({ direction = "right" }))  -- Focus right

-- Vim-like window move
hl.bind(mainMod .. " + SHIFT + H", hl.dsp.window.move({ direction = "left" }))   -- Move window left
hl.bind(mainMod .. " + SHIFT + J", hl.dsp.window.move({ direction = "down" }))   -- Move window down
hl.bind(mainMod .. " + SHIFT + K", hl.dsp.window.move({ direction = "up" }))     -- Move window up
hl.bind(mainMod .. " + SHIFT + L", hl.dsp.window.move({ direction = "right" }))  -- Move window right

-- Window resize
hl.bind(mainMod .. " + SHIFT + U", hl.dsp.exec_cmd("window-double"))                 -- Double window size
hl.bind(mainMod .. " + SHIFT + D", hl.dsp.exec_cmd("window-half"))                   -- Halve window size
hl.bind(mainMod .. " + SHIFT + F", hl.dsp.window.fullscreen({ mode = 1 })) 	     -- Toggle maximize
-- Workspaces: Alt+1..9
for i = 1, 9 do
    hl.bind("ALT + " .. i,         hl.dsp.focus({ workspace = i }))          -- Focus workspace #i
    hl.bind("ALT + SHIFT + " .. i, hl.dsp.window.move({ workspace = i }))    -- Move window to workspace #i
end

-- Window management
hl.bind(mainMod .. " + C", hl.dsp.window.close())                      -- Close window
hl.bind(mainMod .. " + V", hl.dsp.window.float({ action = "toggle" })) -- Toggle floating
hl.bind(mainMod .. " + P", hl.dsp.window.pseudo())                     -- Toggle pseudo-tile
hl.bind(mainMod .. " + N", hl.dsp.exec_cmd("hyprctl dispatch pin"))    -- Toggle window pin (all workspaces)
hl.bind(mainMod .. " + D", hl.dsp.workspace.toggle_special("desktop")) -- Show/hide desktop
hl.bind(mainMod .. " + Num_Lock", hl.dsp.exec_cmd("lock-screen"))      -- Lock screen
hl.bind(mainMod .. " + M", hl.dsp.exit())                              -- Exit Hyprland

-- Scratchpad
hl.bind(mainMod .. " + S",         hl.dsp.workspace.toggle_special("magic"))  -- Show/hide scratchpad
hl.bind(mainMod .. " + SHIFT + S", hl.dsp.exec_cmd("toggle-scratchpad"))       -- Toggle window in/out of scratchpad

-- Screenshot
hl.bind("Pause", hl.dsp.exec_cmd("screenshot")) -- Screenshot (interactive)

-- Keyboard layout
hl.bind(mainMod .. " + SPACE", hl.dsp.exec_cmd("hyprctl switchxkblayout all next")) -- Switch keyboard layout

-- Mouse: drag and resize floating windows
hl.bind(mainMod .. " + mouse:272", hl.dsp.window.drag(),   { mouse = true })
hl.bind(mainMod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })

-- Scroll through workspaces
hl.bind(mainMod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }))
hl.bind(mainMod .. " + mouse_up",   hl.dsp.focus({ workspace = "e-1" }))

-- Media & hardware keys (без комментария — не попадают в подсказку)
hl.bind("XF86AudioRaiseVolume",  hl.dsp.exec_cmd("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"), { locked = true, repeating = true })
hl.bind("XF86AudioLowerVolume",  hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"),      { locked = true, repeating = true })
hl.bind("XF86AudioMute",         hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"),     { locked = true })
hl.bind("XF86AudioMicMute",      hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle"),   { locked = true })
hl.bind("XF86MonBrightnessUp",   hl.dsp.exec_cmd("brightnessctl -e4 -n2 set 5%+"),                  { locked = true, repeating = true })
hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd("brightnessctl -e4 -n2 set 5%-"),                  { locked = true, repeating = true })
hl.bind("XF86AudioNext",         hl.dsp.exec_cmd("playerctl next"),       { locked = true })
hl.bind("XF86AudioPause",        hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPlay",         hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPrev",         hl.dsp.exec_cmd("playerctl previous"),   { locked = true })

-- Hints
hl.bind(mainMod .. " + CTRL + slash", hl.dsp.exec_cmd("show-hints")) -- Toggle keybind hints
