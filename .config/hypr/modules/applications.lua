-- modules/applications.lua

apps = {
terminal     = "kitty",
terminal_ws  = "kitty --class kitty-terminal",
yazi         = "kitty --class kitty-yazi yazi",
yazi_local   = "kitty --class kitty-yazi-local yazi",
browser      = "firefox",
menu         = "wofi --show drun",
monitor      = "kitty --class kitty-btop -o initial_window_width=82c -o initial_window_height=26c btop",
editor       = "code-oss",
editor_local = "code-oss --class code-local",
texter       = "subl",
texter_local = "subl --class subl-local",
}

workspaces = {
main     = "1",
social   = "2",
code     = "3",
virtual  = "4",
terminal = "5",
docs     = "6",
other    = "7",
ext1     = "8",
ext2     = "9",
}