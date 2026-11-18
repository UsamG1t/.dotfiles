# Use powerline
USE_POWERLINE="true"
# Has weird character width
# Example:
#    is not a diamond
HAS_WIDECHARS="false"
# Source manjaro-zsh-configuration
if [[ -e /usr/share/zsh/manjaro-zsh-config ]]; then
  source /usr/share/zsh/manjaro-zsh-config
fi
# Use manjaro zsh prompt
if [[ -e /usr/share/zsh/manjaro-zsh-prompt ]]; then
  source /usr/share/zsh/manjaro-zsh-prompt
fi

# Пользовательские обёртки доступны также в чистой TTY-сессии.
typeset -U path PATH
path=("$HOME/.local/bin" $path)
if [[ -o interactive && -t 1 ]]; then
  "$HOME/.local/bin/fastfetch"
fi

alias vim='nvim'
alias usamg1t-run='source "$HOME/.usamg1t/bin/activate"'

# Machine-specific settings stay outside the repository.
if [[ -r "$HOME/.zshrc.local" ]]; then
  source "$HOME/.zshrc.local"
fi
