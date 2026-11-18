"""Запрос sudo из главного потока curses; в графике используется Polkit."""
import curses
from queue import Empty, Queue
import subprocess
import threading

from gui_mode import console_mode

PROMPTS = Queue()


def run_privileged(command, timeout=120):
    if not console_mode():
        return subprocess.run(['pkexec', *command], capture_output=True, text=True, timeout=timeout)
    ready = subprocess.run(['sudo', '-n', '-v'], capture_output=True, text=True)
    if ready.returncode:
        answer = {'event': threading.Event(), 'ok': False}
        PROMPTS.put(answer)
        if not answer['event'].wait(timeout) or not answer['ok']:
            raise RuntimeError(answer.get('error') or 'Запрос sudo отменён или истёк; действие не выполнено')
    return subprocess.run(['sudo', '-n', '--', *command], capture_output=True, text=True, timeout=timeout)


def process_prompt(screen):
    """Вызывать из основного цикла панели; фоновые задачи не трогают терминал."""
    try:
        answer = PROMPTS.get_nowait()
    except Empty:
        return
    curses.def_prog_mode()
    curses.endwin()
    try:
        with open('/dev/tty', 'r') as terminal_input, open('/dev/tty', 'w') as terminal_output:
            print('Для действия нужны права администратора (Ctrl+C — отмена).', file=terminal_output, flush=True)
            answer['ok'] = subprocess.run(['sudo', '-v'], stdin=terminal_input, stdout=terminal_output, stderr=terminal_output).returncode == 0
    except OSError as error:
        answer['error'] = str(error)
    except KeyboardInterrupt:
        answer['ok'] = False
    finally:
        curses.reset_prog_mode()
        screen.clearok(True)
        answer['event'].set()
