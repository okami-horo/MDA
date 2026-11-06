"""On-demand NIKKE CLI; only an explicit session can request administrator access."""

import argparse
import hashlib
import inspect
import json
from pathlib import Path
import shlex
import sys
import uuid

if __package__:
    from . import nikke_mcp_launcher as launcher
    from .nikke_control import ControlError, NikkeControl, Result, ROOT
else:
    import nikke_mcp_launcher as launcher
    from nikke_control import ControlError, NikkeControl, Result, ROOT


OPERATIONS = {name: name for name in ('status', 'connect', 'observe', 'click', 'drag', 'disconnect', 'battle', 'stop')}
OPERATIONS.update(windows='list_windows', list_windows='list_windows', key='press_key',
                  press_key='press_key', quit='quit', exit='quit', help='help')


class CommandParser(argparse.ArgumentParser):
    def error(self, message):
        raise ControlError('invalid_command', message)


def command_parser():
    parser = CommandParser(prog='nikke', add_help=False)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('status', 'windows', 'disconnect', 'help', 'quit', 'exit', 'stop'):
        commands.add_parser(name, add_help=False)
    observe = commands.add_parser('observe', add_help=False)
    connect = commands.add_parser('connect', add_help=False)
    connect.add_argument('--window-id')
    click = commands.add_parser('click', add_help=False)
    click.add_argument('x', type=int)
    click.add_argument('y', type=int)
    click.add_argument('--button', choices=('left', 'right', 'middle'), default='left')
    drag = commands.add_parser('drag', add_help=False)
    for name in ('from_x', 'from_y', 'to_x', 'to_y'):
        drag.add_argument(name, type=int)
    drag.add_argument('--duration-ms', type=int, default=500)
    key = commands.add_parser('key', add_help=False)
    key.add_argument('key')
    battle = commands.add_parser('battle', add_help=False)
    for command in (click, drag, key, battle):
        command.add_argument('--snapshot', dest='snapshot_id', required=True)
    for command in (observe, click, drag, key):
        command.add_argument('--wait-ms', type=int, default=argparse.SUPPRESS)
    for command in (click, drag, key):
        command.add_argument('--no-screenshot', dest='capture', action='store_false', default=argparse.SUPPRESS)
    return parser


def parse_command(line):
    try:
        if line.lstrip().startswith('{'):
            params = json.loads(line)
            name = params.pop('op')
        else:
            params = vars(command_parser().parse_args(shlex.split(line)))
            name = params.pop('command')
        if not isinstance(name, str) or name not in OPERATIONS:
            raise ValueError('未知操作。')
        operation = OPERATIONS[name]
        if operation in ('quit', 'help'):
            if params:
                raise ValueError('该操作不接受参数。')
        else:
            signature = inspect.signature(getattr(NikkeControl, operation))
            signature.bind(None, **params)
            for name, value in params.items():
                expected = signature.parameters[name].annotation
                if (expected is int and type(value) is not int) or not isinstance(value, expected):
                    raise ValueError(f'{name} 的参数类型无效。')
        return operation, params
    except (ValueError, TypeError, KeyError) as error:
        raise ControlError('invalid_command', str(error)) from error


def emit(result, stdout, image_dir=None, previous_image_digest=None):
    data = dict(result.data)
    digest = previous_image_digest
    if result.image is not None:
        try:
            image_dir.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(result.image).digest()
            destination = image_dir / 'latest.png'
            changed = digest != previous_image_digest or not destination.is_file()
            if changed:
                temporary = image_dir / 'latest.tmp'
                temporary.write_bytes(result.image)
                temporary.replace(destination)
            data['image_path'] = str(destination.resolve())
            data['image_changed'] = changed
            rendered = preview(destination)
            if rendered.data['ok'] and rendered.data['image_bytes'] < rendered.data['source_bytes']:
                data['preview_path'] = rendered.data['image_path']
        except OSError as error:
            digest = None
            data.pop('snapshot_id', None)
            data.update(ok=False, observation_status='failed',
                        input_status=data.get('input_status', 'not_sent'),
                        error={'code': 'image_save_failed', 'message': str(error)})
    print(json.dumps(data, ensure_ascii=False), file=stdout, flush=True)
    result.data = data
    return digest


def run_session(control, *, stdin=None, stdout=None, image_dir=None):
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    image_dir = image_dir or ROOT / '.cache/nikke-control/cli' / uuid.uuid4().hex
    output_lock = control.event_lock
    previous_image_digest = None

    def send(result):
        nonlocal previous_image_digest
        with output_lock:
            previous_image_digest = emit(result, stdout, image_dir, previous_image_digest)

    previous_sink = control.event_sink
    control.event_sink = send
    closed = False
    try:
        send(Result({'ok': True, 'session': 'ready'}))
        for line in stdin:
            if not line.strip():
                continue
            try:
                operation, params = parse_command(line)
            except ControlError as error:
                send(Result({'ok': False, 'input_status': 'not_sent',
                             'error': {'code': error.code, 'message': str(error)}}))
                continue
            if operation == 'help':
                send(Result({'ok': True, 'help': command_parser().format_help(),
                             'input': 'One shell command or JSON object with an op field per line.'}))
                continue
            if operation == 'quit':
                with output_lock:
                    result = control.call('disconnect')
                    if result.data['ok']:
                        closed = True
                        result.data['session'] = 'closed'
                    send(result)
                if closed:
                    return 0
                continue
            # Keep acknowledgement ahead of any very fast completion event.
            with output_lock:
                send(control.call(operation, **params))
    finally:
        if not closed:
            runner = control.battle_runner
            if control.owner != 'manual':
                control.call('stop')
                runner.thread.join(10)
                if runner.thread.is_alive():
                    send(Result({'ok': False, 'session': 'cleanup_pending', 'controller_idle': False}))
                    # Keep native resources isolated on EOF until the worker really stops.
                    while runner.thread.is_alive():
                        runner.thread.join(0.5)
            result = control.call('disconnect')
            result.data['session'] = 'closed' if result.data['ok'] else 'cleanup_failed'
            send(result)
        control.event_sink = previous_sink
    return 0 if result.data['ok'] else 1


def preview(source):
    try:
        from PIL import Image
    except ImportError:
        return Result({'ok': False, 'error': {'code': 'preview_unavailable',
                       'message': 'JPEG 预览需要 Pillow；可直接查看原始 image_path。'}})
    try:
        source = source.resolve()
        destination = source.with_suffix('.preview.jpg')
        temporary = destination.with_name(destination.name + '.tmp')
        with Image.open(source) as image:
            width, height = image.size
            image.convert('RGB').save(temporary, format='JPEG', quality=75, subsampling=0, optimize=True)
        temporary.replace(destination)
        return Result({'ok': True, 'image_path': str(destination), 'source_image_path': str(source),
                       'width': width, 'height': height, 'source_bytes': source.stat().st_size,
                       'image_bytes': destination.stat().st_size})
    except (OSError, ValueError) as error:
        return Result({'ok': False, 'error': {'code': 'image_preview_failed', 'message': str(error)}})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--maa-dir', type=Path, help='Directory containing the MaaFramework DLLs')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status', help='Read runtime/driver diagnostics without UAC or game input')
    commands.add_parser('windows', help='List NIKKE windows without UAC or game input')
    image = commands.add_parser('preview', help='Create a JPEG preview of a local screenshot; needs Pillow, no UAC')
    image.add_argument('image_path', type=Path)
    session = commands.add_parser('session', help='Start an interactive control session; request UAC once',
                                  epilog='Commands: connect, observe, click, drag, key, battle, stop, status, windows, disconnect, quit. '
                                         'Enter help inside the session, or pass JSON lines with an op field.')
    session.add_argument('--no-elevate', action='store_true', help='Inherit current privileges for diagnostics')
    args = parser.parse_args(argv)
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    if args.command == 'preview':
        result = preview(args.image_path)
        emit(result, sys.stdout)
        return 0 if result.data['ok'] else 1
    if args.command == 'session':
        if not args.no_elevate:
            native = launcher.Native()
            if not native.is_admin():
                launcher.bridge(native, args.maa_dir, cli=True)
                return 0
        return run_session(NikkeControl(maa_dir=args.maa_dir))
    control = NikkeControl(maa_dir=args.maa_dir)
    try:
        result = control.call('list_windows' if args.command == 'windows' else 'status')
        emit(result, sys.stdout)
        return 0 if result.data['ok'] else 1
    finally:
        control.call('disconnect')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (launcher.LauncherError, OSError) as error:
        print(f'NIKKE CLI 启动失败：{error}', file=sys.stderr, flush=True)
        sys.exit(1)
