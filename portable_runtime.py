"""Offline dependency selection and launch; no application business logic."""
from pathlib import Path
import argparse
from datetime import datetime
import importlib
import os
import platform
import socket
import subprocess
import sys
import sysconfig
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent


def startup_message(message):
    print(message, flush=True)
    try:
        with (ROOT / 'law_summary_startup.log').open('a', encoding='utf-8') as log:
            log.write(datetime.now().isoformat(timespec='seconds') + ' ' + message + '\n')
    except OSError:
        pass


def prepare_local_settings():
    """Restore a missing default without changing existing application settings."""
    config = ROOT / 'config.json'
    default = ROOT / 'config.example.json'
    if not config.exists() and default.is_file():
        try:
            with config.open('xb') as stream:
                stream.write(default.read_bytes())
        except FileExistsError:
            pass
    if not config.is_file():
        raise RuntimeError('Missing config.json and config.example.json. Extract the entire ZIP again.')
    (ROOT / 'output').mkdir(exist_ok=True)


def prepare_portable():
    vendor = ROOT / 'vendor'
    if not vendor.is_dir():
        return False
    version = sys.version_info[:2]
    if (version != (3, 13) or platform.machine().lower() not in ('amd64', 'x86_64')
            or sys.maxsize <= 2**32 or sys.implementation.name != 'cpython'
            or sysconfig.get_config_var('Py_GIL_DISABLED')):
        raise RuntimeError('Use law_summary.cmd with the included 64-bit Python 3.13.')
    layers = [vendor / f'cp{version[0]}{version[1]}', vendor / 'common']
    if not all(path.is_dir() for path in layers):
        raise RuntimeError('Bundled packages are missing. Extract the complete ZIP first.')
    inherited = set(os.environ.get('PYTHONPATH', '').split(os.pathsep))
    sys.path[:] = [str(p) for p in layers] + [str(ROOT)] + [
        p for p in sys.path if p and p not in inherited and 'site-packages' not in Path(p).parts
        and Path(p).resolve() != ROOT]
    os.environ['PYTHONPATH'] = os.pathsep.join(str(p) for p in layers)
    os.environ['PYTHONNOUSERSITE'] = '1'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['PYTHONUTF8'] = '1'
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.dont_write_bytecode = True
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['LAWTOOL_AUTO_BUILD_CONVERTER'] = '0'
    java = ROOT / 'runtime/java'
    if (java / 'bin/java.exe').is_file():
        os.environ['JAVA_HOME'] = str(java)
        os.environ['PATH'] = str(java / 'bin') + os.pathsep + os.environ.get('PATH', '')
    return True


def check_dependencies(portable):
    modules = ('flask', 'waitress', 'requests', 'httpx', 'openpyxl', 'defusedxml', 'pypdf',
               'markupsafe', 'tzdata')
    for name in modules:
        module = importlib.import_module(name)
        if portable and not Path(module.__file__).resolve().is_relative_to(ROOT / 'vendor'):
            raise RuntimeError('Dependency outside release: ' + name)
    from zoneinfo import ZoneInfo
    ZoneInfo('Asia/Seoul')
    importlib.import_module('webapp.jobs')
    importlib.import_module('html_app')


def available_port(requested):
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', requested))
        except OSError:
            if requested != 8501:
                raise
            sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def open_when_ready(url, process):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(120):
        if process.poll() is not None:
            return
        try:
            with opener.open(url + '/_health', timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            pass
        time.sleep(0.5)


def main():
    # IDE launches and old shortcuts use the same bundled interpreter as the CMD.
    bundled = ROOT / 'runtime/python/python.exe'
    if (ROOT / 'vendor').is_dir() and bundled.is_file() and Path(sys.executable).resolve() != bundled.resolve():
        env = os.environ.copy()
        env.pop('PYTHONHOME', None)
        env['PYTHONPATH'] = ''
        return subprocess.call([str(bundled), '-S', str(ROOT / 'start_web.py'), *sys.argv[1:]], cwd=ROOT, env=env)
    parser = argparse.ArgumentParser(description='law_summary local web launcher')
    parser.add_argument('--check', action='store_true', help='Check bundled runtime and exit')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=8501)
    parser.add_argument('--bundled-python', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--serve', action='store_true', help=argparse.SUPPRESS)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--http', action='store_true')
    mode.add_argument('--xet', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    portable = prepare_portable()
    if portable:
        prepare_local_settings()
        startup_message('Python: ' + sys.executable)
    if portable or args.check:
        check_dependencies(portable)
    if args.check:
        startup_message(f'law_summary runtime OK: Python {platform.python_version()} / bundled={portable}')
        return 0
    if args.serve:
        from html_app import serve
        serve(args.port)
        return 0
    os.environ['EMBED_DOWNLOAD_MODE'] = 'hub' if args.http or args.xet else 'ranges'
    os.environ['HF_HUB_DISABLE_XET'] = '0' if args.xet else '1'
    os.environ.setdefault('HF_XET_HIGH_PERFORMANCE', '1')
    port = available_port(args.port)
    url = f'http://127.0.0.1:{port}'
    startup_message('law_summary: ' + url)
    print('Keep this window open. Press Ctrl+C to stop.', flush=True)
    command = [sys.executable] + (['-S'] if portable else []) + [
        str(ROOT / 'start_web.py'), '--serve', '--port', str(port)]
    child = subprocess.Popen(command, cwd=ROOT)
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(url, child), daemon=True).start()
    try:
        result = child.wait()
        if result:
            startup_message('Web server exited with code ' + str(result))
        return result
    except KeyboardInterrupt:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        return 0
