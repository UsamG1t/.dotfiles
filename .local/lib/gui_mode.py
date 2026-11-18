"""Переключение SDDM/TTY. Привилегированный worker живёт вне графической сессии."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import time
import tomllib
import uuid


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / '.config/gui-mode/services.toml'
RUNTIME = Path('/run/dotfiles-gui-mode')
DISPLAY_MANAGER = 'sddm.service'
GRAPHICAL_ENV = ('DISPLAY', 'WAYLAND_DISPLAY', 'HYPRLAND_INSTANCE_SIGNATURE',
                 'XDG_CURRENT_DESKTOP', 'XDG_SESSION_DESKTOP', 'XDG_SESSION_TYPE', 'XAUTHORITY')


def run(command, *, check=True, timeout=60):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                            env={**os.environ, 'LC_ALL': 'C'})
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or str(command))
    return result


def selection():
    data = tomllib.loads(CONFIG.read_text())
    result = []
    for group in ('system', 'user', 'graphical'):
        for unit in data[group]['units']:
            if not isinstance(unit, str) or not re.fullmatch(r'[A-Za-z0-9_.@:-]+\.(service|socket)', unit):
                raise ValueError(f'Неверное имя службы: {unit!r}')
            entry = ('system' if group == 'system' else 'user', unit, group == 'graphical')
            if entry not in result:
                result.append(entry)
    return result


def atomic_json(destination, value):
    temporary = destination.with_suffix('.new')
    with open(temporary, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o644)
    os.replace(temporary, destination)


def state_path(uid):
    return RUNTIME / f'{uid}.json'


def read_state(uid):
    try:
        return json.loads(state_path(uid).read_text())
    except FileNotFoundError:
        return None


def console_mode():
    """TTY/SSH никогда не пытается открывать графические окна."""
    if os.environ.get('TERM') in ('linux', 'dumb') or os.environ.get('SSH_CONNECTION'):
        return True
    if not (os.environ.get('WAYLAND_DISPLAY') or os.environ.get('DISPLAY')):
        return True
    state = read_state(os.getuid())
    return bool(state and state['phase'] in ('stopping', 'off', 'error-off'))


class Controller:
    def __init__(self, uid):
        self.uid = uid
        self.account = pwd.getpwuid(uid)
        self.state = read_state(uid)

    def user_command(self, *command, check=True, timeout=60):
        if os.geteuid() == self.uid:
            return run(list(command), check=check, timeout=timeout)
        # runuser выставляет HOME/USER/LOGNAME владельца, а не root.
        prefix = ['/usr/bin/runuser', '-u', self.account.pw_name, '--', '/usr/bin/env',
                  f'XDG_RUNTIME_DIR=/run/user/{self.uid}',
                  f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{self.uid}/bus']
        return run([*prefix, *command], check=check, timeout=timeout)

    def ctl(self, scope, *args, check=True):
        command = ['/usr/bin/systemctl', '--no-ask-password', *args]
        if scope == 'user':
            return self.user_command('/usr/bin/systemctl', '--user', '--no-ask-password', *args, check=check)
        return run(command, check=check)

    def unit(self, scope, name):
        result = self.ctl(scope, 'show', name, '--property=LoadState,ActiveState,UnitFileState', check=False)
        if result.returncode and not result.stdout:
            raise RuntimeError(result.stderr.strip())
        return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)

    def sessions(self):
        listing = json.loads(run(['/usr/bin/loginctl', 'list-sessions', '--json=short']).stdout)
        result = []
        for item in listing:
            sid = str(item['session'])
            output = run(['/usr/bin/loginctl', 'show-session', sid,
                          '-p', 'User', '-p', 'Type', '-p', 'Class', '-p', 'State'], check=False).stdout
            props = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
            if props.get('Type') in ('wayland', 'x11') and props.get('Class') == 'user' and props.get('State') != 'closing':
                result.append((sid, int(props['User'])))
        return result

    def registry_units(self):
        output = self.ctl('user', 'list-units', '--type=service', '--state=active',
                          '--plain', '--no-legend', '--no-pager').stdout
        return [line.split()[0] for line in output.splitlines()
                if line.strip() and re.fullmatch(r'dbus-:[A-Za-z0-9_.:-]+-org\.a11y\.atspi\.Registry@\d+\.service', line.split()[0])]

    def bluetooth_power(self):
        if self.unit('system', 'bluetooth.service').get('ActiveState') != 'active':
            return {}
        output = run(['/usr/bin/busctl', '--system', '--json=short', 'call', 'org.bluez', '/',
                      'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects']).stdout
        objects = json.loads(output)['data'][0]
        return {name: interfaces['org.bluez.Adapter1']['Powered']['data']
                for name, interfaces in objects.items() if 'org.bluez.Adapter1' in interfaces}

    def restore_accessibility(self):
        if not self.state.get('registry_active'):
            return
        output = self.user_command('/usr/bin/busctl', '--user', '--json=short', 'call',
                                   'org.a11y.Bus', '/org/a11y/bus', 'org.a11y.Bus', 'GetAddress').stdout
        address = json.loads(output)['data'][0]
        self.user_command('/usr/bin/busctl', '--address=' + address, 'call',
                          'org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                          'StartServiceByName', 'su', 'org.a11y.atspi.Registry', '0')

    def restore_bluetooth(self):
        saved = self.state.get('bluetooth_power', {})
        if not saved:
            return
        deadline = time.monotonic() + 5
        while True:
            adapters = self.bluetooth_power()
            if all(adapter in adapters for adapter in saved) or time.monotonic() >= deadline:
                break
            time.sleep(.1)
        for adapter, powered in saved.items():
            if adapter not in adapters:
                print(f'Адаптер {adapter} отсутствует; состояние радио не восстановлено', flush=True)
                continue
            result = run(['/usr/bin/busctl', '--system', 'set-property', 'org.bluez', adapter,
                          'org.bluez.Adapter1', 'Powered', 'b', 'true' if powered else 'false'], check=False)
            if result.returncode:
                # Например, аппаратный rfkill изменился, пока графика была выключена.
                print(f'Не восстановлено питание {adapter}: {result.stderr.strip()}', flush=True)

    def save(self, phase=None):
        if phase:
            self.state['phase'] = phase
        atomic_json(state_path(self.uid), self.state)

    def remember(self, scope, name, graphical=False):
        if any(item['scope'] == scope and item['name'] == name for item in self.state['units']):
            return
        props = self.unit(scope, name)
        active = props.get('ActiveState') in ('active', 'activating', 'reloading')
        masked = props.get('UnitFileState', '').startswith('masked')
        self.state['units'].append(dict(scope=scope, name=name, graphical=graphical,
                                       active=active, masked=masked,
                                       missing=props.get('LoadState') == 'not-found',
                                       mask_added=False, restored=False))

    def stop_selected(self):
        # Сначала блокируем ВСЕ источники активации, затем останавливаем процессы.
        for item in self.state['units']:
            if item['missing'] or item['masked']:
                continue
            if not item['mask_added']:
                item['mask_added'] = True
                self.save()  # Намерение записано и при сбое между mask и следующей записью.
                self.ctl(item['scope'], '--runtime', 'mask', item['name'])
                if not self.unit(item['scope'], item['name']).get('UnitFileState', '').startswith('masked'):
                    raise RuntimeError('Не удалось временно заблокировать ' + item['name'])
            item['restored'] = False
        self.save()
        for scope in ('user', 'system'):
            names = [item['name'] for item in self.state['units'] if item['scope'] == scope and not item['missing']]
            if names:
                self.ctl(scope, 'stop', *names)
                for name in names:
                    if self.unit(scope, name).get('ActiveState') not in ('inactive', 'failed'):
                        raise RuntimeError('Служба не остановлена: ' + name)
        # Registry создаётся D-Bus с динамическим именем. Сам bus уже заблокирован,
        # оставшиеся Registry останавливаем без маскирования случайного имени.
        registry = self.registry_units()
        if registry:
            self.ctl('user', 'stop', *registry)

    def off(self, strict, vt):
        sessions = self.sessions()
        if any(uid != self.uid for _, uid in sessions):
            raise RuntimeError('Открыта графическая сессия другого пользователя; SDDM не остановлен')
        for sid, _ in sessions:
            current_vt = run(['/usr/bin/loginctl', 'show-session', sid, '-p', 'VTNr', '--value']).stdout.strip()
            if current_vt == str(vt):
                raise RuntimeError(f'tty{vt} занята графической сессией; выберите другую через --vt')
        linger = run(['/usr/bin/loginctl', 'show-user', str(self.uid), '--property=Linger', '--value']).stdout.strip()
        if linger != 'yes':
            raise RuntimeError('Для сохранения user-служб нужен Linger=yes; настройте его перед gui-off')
        if self.unit('system', DISPLAY_MANAGER).get('LoadState') == 'not-found':
            raise RuntimeError('Не установлен SDDM')
        if sessions and self.unit('system', DISPLAY_MANAGER).get('ActiveState') != 'active':
            raise RuntimeError('Найдена графическая сессия вне работающего SDDM; она не будет закрыта')
        if not self.state or self.state['phase'] == 'on':
            self.state = dict(id=uuid.uuid4().hex, uid=self.uid, phase='stopping', strict=False,
                              units=[], sessions=[sid for sid, _ in sessions],
                              display_stopped=False,
                              display_active=self.unit('system', DISPLAY_MANAGER).get('ActiveState') == 'active')
            # Снимок до обычного off тоже позволяет позже добавить --strict,
            # сохранив состояние, существовавшее до завершения рабочего стола.
            for scope, name, graphical in selection():
                self.remember(scope, name, graphical)
            self.state['bluetooth_power'] = self.bluetooth_power()
            self.state['registry_active'] = bool(self.registry_units())
        if self.state['phase'] in ('restoring', 'awaiting-login', 'error-on'):
            raise RuntimeError('Сначала завершите восстановление через gui-on')
        # Снимок всех служб собирается до первого изменения. Повтор не затирает его.
        if strict:
            for item in self.state['units']:
                if item['active'] and item['masked']:
                    raise RuntimeError('Активная служба имеет чужую mask: ' + item['name'])
            self.state['strict'] = True
        self.state.pop('error', None)
        self.save('stopping')
        self.ctl('system', 'start', f'getty@tty{vt}.service')
        if self.unit('system', f'getty@tty{vt}.service').get('ActiveState') != 'active':
            raise RuntimeError('Не удалось подготовить консоль')
        self.user_command('/usr/bin/python3', str(ROOT / '.local/bin/calendar-popup'), '--pause-and-stop')
        # Маски strict ставим до завершения клиентов, чтобы они не перезапустили BlueZ/звук.
        if self.state['strict']:
            self.stop_selected()
        run(['/usr/bin/chvt', str(vt)])
        self.state['display_stopped'] = True
        self.save()
        self.ctl('system', 'stop', DISPLAY_MANAGER)
        # SDDM обычно закрывает сессию сам. Оставшиеся процессы убираются только
        # из её logind scope, без kill-user и без затрагивания TTY/SSH/user@UID.
        for sid, uid in sessions:
            if uid == self.uid:
                run(['/usr/bin/loginctl', 'terminate-session', sid], check=False)
        self.user_command('/usr/bin/dbus-update-activation-environment', '--systemd',
                          *(name + '=' for name in GRAPHICAL_ENV))
        self.ctl('user', 'unset-environment', *GRAPHICAL_ENV)
        self.save('off')
        print(f'Графика остановлена. Консоль tty{vt}; возврат: gui-on', flush=True)

    def restore_units(self, graphical):
        if not self.state['strict']:
            return
        items = [item for item in self.state['units'] if item['graphical'] == graphical and not item['missing']]
        # Нельзя запускать PipeWire, пока ещё заблокированы его зависимости/сокеты.
        for item in items:
            if item['mask_added']:
                self.ctl(item['scope'], '--runtime', 'unmask', item['name'])
                item['mask_added'] = False
                self.save()
        for scope in ('system', 'user'):
            active = [item['name'] for item in items if item['scope'] == scope and item['active'] and not item['restored']]
            if active:
                self.ctl(scope, 'start', *active)
                for name in active:
                    if self.unit(scope, name).get('ActiveState') != 'active':
                        raise RuntimeError('Не восстановлена служба ' + name)
            for item in items:
                if item['scope'] == scope:
                    item['restored'] = True
            self.save()

    def session_ready(self):
        try:
            marker = json.loads(Path(f'/run/user/{self.uid}/gui-session-ready.json').read_text())
        except (OSError, ValueError):
            return False
        return any(uid == self.uid and sid == marker.get('session')
                   and (sid not in self.state['sessions'] or not self.state['display_stopped'])
                   for sid, uid in self.sessions())

    def on(self):
        if not self.state:
            if self.unit('system', DISPLAY_MANAGER).get('UnitFileState', '').startswith('masked'):
                raise RuntimeError('SDDM заблокирован вручную; gui-on не снимает чужую mask')
            self.ctl('system', 'start', DISPLAY_MANAGER)
            return
        if self.state['phase'] == 'on':
            if self.state['display_active']:
                self.ctl('system', 'start', DISPLAY_MANAGER)
            print('Предыдущее восстановление уже завершено', flush=True)
            return
        self.state.pop('error', None)
        self.save('restoring')
        self.restore_units(False)
        if self.state['strict']:
            self.restore_bluetooth()
        if self.state['display_active']:
            self.ctl('system', 'start', DISPLAY_MANAGER)
        pending = [item for item in self.state['units'] if item['graphical'] and not item['missing']] if self.state['strict'] else []
        # Неактивные ранее службы тоже нужно разблокировать, но не запускать.
        if pending and self.state['display_active']:
            self.save('awaiting-login')
            deadline = time.monotonic() + 600
            while not self.session_ready():
                if time.monotonic() >= deadline:
                    raise RuntimeError('За 10 минут не выполнен вход в Hyprland. После входа повторите gui-on')
                time.sleep(1)
        self.restore_units(True)
        if self.state['strict']:
            self.restore_accessibility()
        self.save('on')
        print('Прежнее состояние служб восстановлено', flush=True)

    def check(self, strict):
        print('SDDM:', self.unit('system', DISPLAY_MANAGER).get('ActiveState', 'unknown'))
        linger = run(['/usr/bin/loginctl', 'show-user', str(self.uid), '--property=Linger', '--value']).stdout.strip()
        print('Linger:', linger)
        if linger != 'yes':
            raise RuntimeError('User-службы должны переживать выход: требуется Linger=yes')
        for sid, uid in self.sessions():
            print(f'Графическая сессия: {sid}, uid={uid}')
            if uid != self.uid:
                raise RuntimeError('Открыта графическая сессия другого пользователя')
        if strict:
            for scope, name, _ in selection():
                props = self.unit(scope, name)
                print(f"{scope}: {name}: {props.get('ActiveState')} / {props.get('UnitFileState', props.get('LoadState'))}")
        print('Проверка чтения состояния завершена; ничего не изменено.')


def mark_session_ready():
    """Вызывается из Hyprland после появления нового дисплея, без sudo."""
    if not os.environ.get('WAYLAND_DISPLAY') or not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        raise RuntimeError('--session-ready вызывается внутри Hyprland')
    assignments = [name + '=' + os.environ.get(name, '') for name in GRAPHICAL_ENV]
    run(['/usr/bin/dbus-update-activation-environment', '--systemd', *assignments])
    runtime = Path(f'/run/user/{os.getuid()}')
    atomic_json(runtime / 'gui-session-ready.json', {'session': os.environ.get('XDG_SESSION_ID', '')})


def worker(uid, mode, strict, vt):
    if os.geteuid() != 0 or uid <= 0:
        raise RuntimeError('Внутренний worker запускается только через sudo systemd-run')
    RUNTIME.mkdir(mode=0o755, exist_ok=True)
    if RUNTIME.is_symlink() or RUNTIME.stat().st_uid != 0:
        raise RuntimeError('Небезопасный ' + str(RUNTIME))
    with open(RUNTIME / 'lock', 'a') as lock:
        os.fchmod(lock.fileno(), 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Уже выполняется другое переключение GUI')
        controller = Controller(uid)
        try:
            if mode == 'off':
                controller.off(strict, vt)
            else:
                controller.on()
        except Exception as error:
            if controller.state:
                controller.state['error'] = str(error)
                controller.save('error-' + mode)
            raise


def main(mode):
    parser = argparse.ArgumentParser(description='Отключить графику' if mode == 'off' else 'Вернуть графику и прежние службы')
    parser.add_argument('--dry-run', action='store_true', help='Показать действия без sudo и изменений')
    parser.add_argument('--status', action='store_true', help='Показать сохранённое состояние переключения')
    parser.add_argument('--check', action='store_true', help='Проверить доступ к службам и сессиям без изменений')
    if mode == 'off':
        parser.add_argument('--strict', action='store_true', help='Также временно остановить службы из services.toml')
        parser.add_argument('--vt', type=int, choices=range(2, 13), default=3, metavar='2..12', help='Консоль для перехода (по умолчанию tty3)')
    else:
        parser.add_argument('--session-ready', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--worker', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if getattr(args, 'session_ready', False):
            mark_session_ready()
            return
        uid = args.worker if args.worker is not None else os.getuid()
        if args.status:
            state = read_state(uid)
            if state:
                summary = dict(phase=state['phase'], strict=state['strict'],
                               masked_units=sum(item['mask_added'] for item in state['units']))
                if state.get('error'):
                    summary['error'] = state['error']
            else:
                summary = {'phase': 'unknown', 'message': 'Сохранённого переключения нет'}
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return
        if args.check:
            Controller(uid).check(getattr(args, 'strict', False))
            return
        if args.dry_run:
            if mode == 'off':
                print(f'Подготовить tty{args.vt}; приостановить таймер; остановить SDDM и его графические сессии.')
                if args.strict:
                    for scope, unit, _ in selection():
                        print(f'  {scope}: runtime mask + stop {unit}')
            else:
                print('Снять свои runtime mask; вернуть ранее активные службы и SDDM; после входа вернуть порталы и accessibility.')
            return
        if args.worker is not None:
            worker(uid, mode, getattr(args, 'strict', False), getattr(args, 'vt', 3))
            return
        if uid == 0:
            raise RuntimeError('Запускайте без sudo: скрипт сам запросит права перед переключением')
        if mode == 'on' and os.environ.get('WAYLAND_DISPLAY') and os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') and not os.environ.get('SSH_CONNECTION') and os.environ.get('TERM') != 'linux':
            mark_session_ready()
        job = f'dotfiles-gui-mode-{uid}'
        active = run(['/usr/bin/systemctl', 'is-active', job + '.service'], check=False).stdout.strip()
        if active in ('active', 'activating', 'deactivating'):
            print(f'Переключение ещё выполняется. Проверьте gui-{mode} --status; новая задача не запущена.')
            return
        # Root-служба не зависит от терминала и logind scope закрываемого рабочего стола.
        command = ['sudo', '--', '/usr/bin/systemd-run', f'--unit={job}',
                   '--collect', '--service-type=exec', '--property=RuntimeMaxSec=15min',
                   '/usr/bin/python3', '-I', '-B', str(ROOT / f'.local/bin/gui-{mode}'), '--worker', str(uid)]
        if mode == 'off':
            command += ['--vt', str(args.vt)]
            if args.strict:
                command.append('--strict')
        print(f'Запускается gui-{mode}. Состояние: gui-{mode} --status; журнал: journalctl -u dotfiles-gui-mode-{uid}', flush=True)
        subprocess.run(command, check=True)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'gui-{mode}: {error}', file=sys.stderr)
        sys.exit(1)
