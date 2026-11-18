"""Локальная повестка и таймер календарной панели. Только стандартная библиотека."""

from contextlib import contextmanager
from datetime import date, timedelta
import fcntl
import json
import math
import os
from pathlib import Path
import re
import select
import signal
import socket
import struct
import tempfile
import time
import uuid


def paths():
    custom = os.environ.get('CALENDAR_POPUP_DIR')
    if custom:
        base = Path(custom).expanduser()
        data, state, runtime = base / 'data', base / 'state', base / 'run'
    else:
        data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'calendar-popup'
        state = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'calendar-popup'
        runtime = Path(os.environ.get('XDG_RUNTIME_DIR', '/dev/shm')) / f'calendar-popup-{os.getuid()}'
    return {'agenda': data / 'agenda.json', 'timer': state / 'timer.json', 'runtime': runtime}


def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.stat().st_uid != os.getuid():
        raise ValueError(f'Небезопасный каталог: {path}')
    path.chmod(0o700)


def atomic_json(path, value):
    private_dir(path.parent)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Agenda:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {'tasks': [], 'dates': []}
        private_dir(self.path.parent)
        if not self.path.exists():
            with self.lock():
                if not self.path.exists():
                    atomic_json(self.path, self.data)
        self.reload()

    @contextmanager
    def lock(self):
        fd = os.open(self.path.with_suffix('.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def reload(self):
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict):
                raise ValueError('ожидается JSON-объект')
            for group in ('tasks', 'dates'):
                items = data.setdefault(group, [])
                if not isinstance(items, list):
                    raise ValueError(f'{group} должен быть списком')
                for item in items:
                    if not isinstance(item, dict) or not isinstance(item.get('text'), str) or not item['text'].strip():
                        raise ValueError('у записи должны быть дата date и текст text')
                    date.fromisoformat(item['date'])
                    if group == 'tasks' and not isinstance(item.get('done', False), bool):
                        raise ValueError('done должен быть true/false')
                    if group == 'dates' and not isinstance(item.get('annual', False), bool):
                        raise ValueError('annual должен быть true/false')
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError(f'{self.path}: {error}. Файл не изменён') from error
        self.data = data

    def tasks(self, day):
        return [item for item in self.data['tasks'] if item['date'] == day.isoformat()]

    def events(self, day):
        return [item for item in self.data['dates'] if (item['date'][5:] == day.isoformat()[5:] if item.get('annual') else item['date'] == day.isoformat())]

    def add(self, day, text, event=False, annual=False):
        if not text.strip():
            raise ValueError('Введите текст')
        with self.lock():
            self.reload()
            item = {'id': uuid.uuid4().hex, 'date': day.isoformat(), 'text': text.strip()}
            item.update({'annual': annual} if event else {'done': False})
            self.data['dates' if event else 'tasks'].append(item)
            atomic_json(self.path, self.data)

    def change(self, day, index, delete=False):
        # Повторно читаем файл под блокировкой, чтобы сохранить сторонние добавления.
        selected = self.tasks(day)[index]
        with self.lock():
            self.reload()
            item = next((t for t in self.data['tasks'] if (t.get('id') == selected['id'] if selected.get('id') else t == selected)), None)
            if item is None:
                raise ValueError('Задача уже изменена; обновите список')
            if delete:
                self.data['tasks'].remove(item)
            else:
                item['done'] = not item.get('done', False)
            atomic_json(self.path, self.data)


def duration(text):
    """Минуты, 1h30m, 90s, MM:SS или HH:MM:SS."""
    text = text.strip().lower().replace(',', '.')
    if ':' in text:
        parts = text.split(':')
        if len(parts) not in (2, 3) or any(not p.isdigit() for p in parts) or any(int(p) >= 60 for p in parts[1:]):
            raise ValueError('Формат времени: MM:SS или HH:MM:SS')
        seconds = sum(int(value) * 60 ** i for i, value in enumerate(reversed(parts)))
    elif re.fullmatch(r'\d+(?:\.\d+)?', text):
        seconds = float(text) * 60
    else:
        text = text.replace('мин', 'm').replace('ч', 'h').replace('м', 'm').replace('с', 's').replace(' ', '')
        matches = list(re.finditer(r'(\d+(?:\.\d+)?)([hms])', text))
        if not matches or ''.join(m.group() for m in matches) != text:
            raise ValueError('Примеры: 5, 1h30m, 90s, 05:00')
        seconds = sum(float(m[1]) * {'h': 3600, 'm': 60, 's': 1}[m[2]] for m in matches)
    if not math.isfinite(seconds) or not 1 <= seconds <= 365 * 86400:
        raise ValueError('Продолжительность: от секунды до года')
    return math.ceil(seconds)


def clock():
    return time.clock_gettime(time.CLOCK_BOOTTIME)


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


class Timer:
    def __init__(self, path, now=clock, wall=time.time, boot=boot_id):
        self.path, self.now, self.wall, self.boot = Path(path), now, wall, boot
        self.state = {'status': 'idle', 'mode': 'timer', 'phase': 'timer', 'completed': 0,
                      'seconds': 1500, 'remaining': 1500, 'snoozing': False,
                      'settings': {'work': 1500, 'short': 300, 'long': 900, 'rounds': 4}, 'id': ''}
        if self.path.exists():
            saved = json.loads(self.path.read_text())
            if not isinstance(saved, dict) or saved.get('status') not in ('idle', 'running', 'paused', 'alarm'):
                raise ValueError(f'Неверное состояние таймера: {self.path}')
            self.state.update(saved)
        if self.state['status'] == 'running' and self.state.get('boot') != self.boot():
            self.state['due'] = self.now() + max(0, self.state['due_wall'] - self.wall())
            self.state['boot'] = self.boot()

    def save(self):
        atomic_json(self.path, self.state)

    def remaining(self):
        return max(0, self.state['due'] - self.now()) if self.state['status'] == 'running' else self.state.get('remaining', 0)

    def snapshot(self):
        return {**self.state, 'remaining': math.ceil(self.remaining())}

    def schedule(self, seconds, snoozing=False):
        self.state.update(status='running', seconds=seconds, remaining=seconds, snoozing=snoozing,
                          due=self.now() + seconds, due_wall=self.wall() + seconds, boot=self.boot(), id=uuid.uuid4().hex)

    def tick(self):
        if self.state['status'] == 'running' and self.remaining() <= 0:
            self.state.update(status='alarm', remaining=0)
            self.save()
            return True
        return False

    def command(self, action, **args):
        if action == 'status':
            return self.snapshot()
        if action == 'settings':
            settings = {key: int(args[key]) for key in ('work', 'short', 'long', 'rounds')}
            if any(not 1 <= settings[key] <= 86400 for key in ('work', 'short', 'long')) or not 1 <= settings['rounds'] <= 99:
                raise ValueError('Неверные интервалы Pomodoro')
            self.state['settings'] = settings
        elif action == 'start':
            mode = args.get('mode', 'timer')
            if mode not in ('timer', 'pomodoro'):
                raise ValueError('Неизвестный режим таймера')
            seconds = float(args.get('seconds', self.state['settings']['work'])) if mode == 'timer' else self.state['settings']['work']
            if not math.isfinite(seconds) or not 1 <= seconds <= 365 * 86400:
                raise ValueError('Неверная длительность')
            self.state.update(mode=mode, phase='timer' if mode == 'timer' else 'work', completed=0)
            self.schedule(seconds)
        elif action == 'pause':
            if self.state['status'] == 'running':
                self.state.update(remaining=self.remaining(), status='paused')
            elif self.state['status'] == 'alarm':
                self.state.update(remaining=0, status='paused')
        elif action == 'resume':
            if self.state['status'] == 'paused':
                self.schedule(self.state['remaining'], self.state.get('snoozing', False))
        elif action == 'stop':
            if 'id' in args and args['id'] != self.state['id']:
                raise ValueError('Это напоминание уже закрыто')
            self.state.update(status='idle', remaining=0, snoozing=False, id='')
        elif action in ('dismiss', 'snooze'):
            if self.state['status'] != 'alarm' or args.get('id') != self.state['id']:
                raise ValueError('Это напоминание уже закрыто')
            if action == 'snooze':
                seconds = float(args.get('seconds', 300))
                if not math.isfinite(seconds) or not 1 <= seconds <= 86400:
                    raise ValueError('Неверная отсрочка')
                self.schedule(seconds, True)
            elif self.state['mode'] == 'timer':
                self.state.update(status='idle', remaining=0, id='', snoozing=False)
            else:
                settings = self.state['settings']
                if self.state['phase'] == 'work':
                    self.state['completed'] += 1
                    phase = 'long' if self.state['completed'] % settings['rounds'] == 0 else 'short'
                else:
                    phase = 'work'
                self.state['phase'] = phase
                self.schedule(settings[phase])
        else:
            raise ValueError('Неизвестная команда')
        self.save()
        return self.snapshot()


def request(action='status', _peer=False, **args):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(1.5)
        client.connect(str(paths()['runtime'] / 'control.sock'))
        if _peer:
            peer = struct.unpack('3i', client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
        client.sendall((json.dumps({'action': action, **args}) + '\n').encode())
        data = b''
        while not data.endswith(b'\n') and len(data) < 65536:
            part = client.recv(65536)
            if not part:
                break
            data += part
    response = json.loads(data)
    if 'error' in response:
        raise ValueError(response['error'])
    return (response['state'], peer) if _peer else response['state']


def serve(alarm_callback):
    """Один фоновый процесс на пользователя; GUI обращается к нему по приватному сокету."""
    locations = paths()
    runtime = locations['runtime']
    private_dir(runtime)
    fd = os.open(runtime / 'daemon.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        timer = Timer(locations['timer'])
        address = runtime / 'control.sock'
        address.unlink(missing_ok=True)
        alarm_process, announced, retry_at = None, '', 0
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(address))
            address.chmod(0o600)
            server.listen(8)
            server.settimeout(.2)
            try:
                while True:
                    timer.tick()
                    state = timer.snapshot()
                    if state['status'] == 'alarm':
                        if state['id'] != announced or ((alarm_process is None or alarm_process.poll() is not None) and time.monotonic() > retry_at):
                            try:
                                alarm_process = alarm_callback(state)
                            except OSError:
                                alarm_process = None
                            announced = state['id']
                            retry_at = time.monotonic() + 15
                    else:
                        announced = ''
                    try:
                        client, _ = server.accept()
                    except socket.timeout:
                        continue
                    with client:
                        client.settimeout(.5)
                        shutdown = False
                        try:
                            data = b''
                            while b'\n' not in data and len(data) <= 8192:
                                part = client.recv(8192)
                                if not part:
                                    break
                                data += part
                            if len(data) > 8192 or not data.endswith(b'\n'):
                                raise ValueError('Неверный запрос')
                            args = json.loads(data)
                            if not isinstance(args, dict):
                                raise ValueError('Запрос должен быть объектом')
                            action = args.pop('action')
                            timer.tick()
                            shutdown = action == 'shutdown'
                            response = {'state': timer.command('pause' if shutdown else action, **args)}
                        except (ValueError, TypeError, KeyError, OSError) as error:
                            response = {'error': str(error)}
                        try:
                            client.sendall((json.dumps(response) + '\n').encode())
                        except OSError:
                            pass
                        if shutdown and 'error' not in response:
                            if alarm_process is not None and alarm_process.poll() is None:
                                alarm_process.terminate()
                            return
            finally:
                address.unlink(missing_ok=True)


def pause_and_stop():
    """Остановить daemon с сохранением таймера; отсутствие daemon — штатный случай."""
    try:
        request('shutdown')
        deadline = time.monotonic() + 5
        while (paths()['runtime'] / 'control.sock').exists() and time.monotonic() < deadline:
            time.sleep(.05)
        if (paths()['runtime'] / 'control.sock').exists():
            raise RuntimeError('Таймер не подтвердил остановку')
        return
    except (ConnectionRefusedError, FileNotFoundError):
        pass
    except ValueError as error:
        if str(error) != 'Неизвестная команда':
            raise
        # Уже запущенная старая версия не знает shutdown. Сначала получает pause,
        # затем завершается конкретный владелец сокета; посторонние Python не трогаем.
        _, (pid, uid, _) = request('pause', _peer=True)
        if uid != os.getuid() or pid == os.getpid():
            raise RuntimeError('Неожиданный владелец сокета календаря')
        descriptor = os.pidfd_open(pid)
        try:
            script = Path(__file__).resolve().parents[2] / 'bin/calendar-popup'
            arguments = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
            if b'--daemon' not in arguments or not any(arg.endswith(b'/calendar-popup') and Path(os.fsdecode(arg)).resolve() == script for arg in arguments):
                raise RuntimeError('Сокет принадлежит постороннему процессу')
            signal.pidfd_send_signal(descriptor, signal.SIGTERM)
            if not select.select([descriptor], [], [], 5)[0]:
                raise RuntimeError('Старая версия таймера не завершилась')
        finally:
            os.close(descriptor)
    # Файл мог остаться от завершившегося daemon. Не создаём пустой таймер.
    runtime = paths()['runtime']
    private_dir(runtime)
    fd = os.open(runtime / 'daemon.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Таймер работает, но управляющий сокет недоступен')
        (runtime / 'control.sock').unlink(missing_ok=True)
        if paths()['timer'].exists():
            Timer(paths()['timer']).command('pause')
