"""Local Windows launcher; the bundled Python executes this file."""
import ctypes
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait_ready(url, process=None):
    for _ in range(180):
        if process is not None and process.poll() is not None:
            raise RuntimeError('De spellingcontrole kon niet starten. Zie languagetool.log.')
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError('Het starten duurt te lang. Zie de logbestanden in de gegevensmap.')


def windows_job():
    """Closing the launcher also closes Java, including closing the console X."""
    from ctypes import wintypes
    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ('ro', 'wo', 'oo', 'rb', 'wb', 'ob')]
    class BASIC(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                    ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                    ('active', wintypes.DWORD), ('affinity', ctypes.c_size_t),
                    ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
    class EXTENDED(ctypes.Structure):
        _fields_ = [('basic', BASIC), ('io', IO), ('process_memory', ctypes.c_size_t),
                    ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    handle = kernel.CreateJobObjectW(None, None)
    limits = EXTENDED()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not handle or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def main():
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    mutex = kernel.CreateMutexW(None, False, 'Local\\VKVDocumentcontrole')
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        input('VKV Documentcontrole is al geopend. Gebruik het bestaande venster. Druk op Enter.\n')
        return
    root = Path(__file__).resolve().parent
    os.chdir(root)
    data = Path(os.environ['LOCALAPPDATA']) / 'VKV-mag' / 'data'
    data.mkdir(parents=True, exist_ok=True)
    fonts = data / 'fonts'
    fonts.mkdir(exist_ok=True)
    for source in (root / 'storage' / 'fonts').glob('*'):
        if source.is_file() and not (fonts / source.name).exists():
            shutil.copy2(source, fonts / source.name)
    app_port, lt_port = free_port(), free_port()
    while app_port == lt_port:
        lt_port = free_port()
    os.environ.update(UPLOAD_DIR=str(data / 'uploads'), TEMP_DIR=str(data / 'temporary'),
                      FONT_DIR=str(fonts), LANGUAGETOOL_URL=f'http://127.0.0.1:{lt_port}')
    job = windows_job()
    print('VKV Documentcontrole wordt gestart. De eerste start kan even duren.', flush=True)
    print(f'Gegevens en logs: {data}', flush=True)
    with (data / 'languagetool.log').open('w', encoding='utf-8') as log:
        java = subprocess.Popen([str(root / 'java' / 'bin' / 'java.exe'), '-Xmx1024m',
                                 '-cp', str(root / 'languagetool' / 'languagetool-server.jar'),
                                 'org.languagetool.server.HTTPServer', '--port', str(lt_port)],
                                cwd=root / 'languagetool', stdout=log, stderr=log,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        server = None
        try:
            wait_ready(f'http://127.0.0.1:{lt_port}/v2/languages', java)
            import uvicorn
            from app.main import app
            server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=app_port, log_level='warning'))
            thread = threading.Thread(target=server.run, daemon=True)
            thread.start()
            url = f'http://127.0.0.1:{app_port}'
            wait_ready(url)
            webbrowser.open(url)
            print(f'Open zo nodig zelf: {url}', flush=True)
            try:
                input('Laat dit venster open tijdens het werken. Druk op Enter om de app te sluiten.\n')
            except EOFError:
                pass
        finally:
            if server is not None:
                server.should_exit = True
                thread.join(timeout=15)
            java.terminate()
            try:
                java.wait(timeout=10)
            except subprocess.TimeoutExpired:
                java.kill()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print(f'VKV kon niet starten: {error}', flush=True)
        try:
            input('Druk op Enter om dit venster te sluiten.\n')
        except EOFError:
            pass
