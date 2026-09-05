-- ~/.config/nvim-hint/init.lua
-- Minimal read-only viewer for keybind hints.
--
-- Available actions:
--   j / k           scroll line by line
--   Ctrl-d / Ctrl-u scroll half page
--   G / gg          jump to end / beginning
--   /               search forward  (n / N for next / previous match)
--   Esc             clear search highlight
--   q               close window
--   Super+Shift+/   close window (from Hyprland, works regardless of focus)

-- ── Disable built-in file browser and other heavy plugins ─────────────────────
vim.g.loaded_netrw            = 1
vim.g.loaded_netrwPlugin      = 1
vim.g.loaded_matchparen       = 1

-- ── Appearance ─────────────────────────────────────────────────────────────────
vim.opt.termguicolors  = true
vim.opt.background     = "dark"
vim.opt.number         = false
vim.opt.relativenumber = false
vim.opt.signcolumn     = "no"
vim.opt.ruler          = false
vim.opt.showmode       = false
vim.opt.showcmd        = false
vim.opt.laststatus     = 0       -- hide statusline
vim.opt.showtabline    = 0       -- hide tabline
vim.opt.wrap           = false
vim.opt.cursorline     = true
vim.opt.fillchars      = { eob = " " }  -- no ~ on empty lines

vim.opt.wrap      = true
vim.opt.linebreak = true

-- Transparent background so Hyprland's window opacity shines through cleanly
vim.api.nvim_set_hl(0, "Normal",      { bg = "NONE" })
vim.api.nvim_set_hl(0, "NormalNC",    { bg = "NONE" })
vim.api.nvim_set_hl(0, "EndOfBuffer", { bg = "NONE" })

-- ── Read-only & no swap ────────────────────────────────────────────────────────
vim.opt.readonly   = true
vim.opt.modifiable = false
vim.opt.swapfile   = false

-- ── Search ─────────────────────────────────────────────────────────────────────
vim.opt.hlsearch   = true
vim.opt.incsearch  = true
vim.opt.ignorecase = true
vim.opt.smartcase  = true

-- ── Keymaps ────────────────────────────────────────────────────────────────────
local nmap = function(lhs, rhs)
    vim.keymap.set("n", lhs, rhs, { noremap = true, silent = true })
end

nmap("q",     function() vim.cmd("q!") end)
nmap("<Esc>", function() vim.cmd("nohlsearch") end)
nmap(":", "<Nop>")
local noop_keys = {
    "i", "I", "a", "A", "o", "O",   -- insert
    "s", "S", "c", "C",              -- change
    "d", "D", "x", "X",             -- delete
    "r", "R",                        -- replace
    "u", "U",                        -- undo (file is readonly anyway)
    "p", "P",                        -- paste
}
for _, key in ipairs(noop_keys) do
    nmap(key, "<Nop>")
end
