"""Build a self-contained Windows x64 installer on Linux using NSIS."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
import httpx

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / 'build'
PAYLOAD = BUILD / 'payload'


def download(url, target, checksum=None):
    if not target.exists():
        with httpx.stream('GET', url, follow_redirects=True, timeout=120) as response:
            response.raise_for_status()
            temporary = target.with_suffix('.download')
            with temporary.open('wb') as output:
                for block in response.iter_bytes():
                    output.write(block)
            temporary.replace(target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if checksum and checksum != digest:
        raise ValueError(f'Checksum mismatch: {target}')
    return {'url': url, 'sha256': digest}


def main():
    PAYLOAD.mkdir(parents=True, exist_ok=True)
    (ROOT / 'dist').mkdir(exist_ok=True)
    manifest = {}
    python_url = 'https://www.python.org/ftp/python/3.13.7/python-3.13.7-embed-amd64.zip'
    manifest['python'] = download(python_url, BUILD / 'python.zip')
    with zipfile.ZipFile(BUILD / 'python.zip') as archive:
        archive.extractall(PAYLOAD / 'python')
    (PAYLOAD / 'python' / 'python313._pth').write_text('python313.zip\n.\nLib/site-packages\n..\nimport site\n')
    api = 'https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jre&os=windows&vendor=eclipse'
    response = httpx.get(api, timeout=60)
    response.raise_for_status()
    package = response.json()[0]['binary']['package']
    java_zip = BUILD / (package['checksum'] + '.zip')
    manifest['java'] = download(package['link'], java_zip, package['checksum'])
    with zipfile.ZipFile(java_zip) as archive:
        archive.extractall(BUILD / 'java-unpacked')
        top = archive.namelist()[0].split('/')[0]
    shutil.copytree(BUILD / 'java-unpacked' / top, PAYLOAD / 'java', dirs_exist_ok=True)
    requirements = [line.replace('uvicorn[standard]', 'uvicorn')
                    for line in (ROOT.parent / 'requirements.txt').read_text().splitlines()
                    if line and line != 'pytest']
    subprocess.run([sys.executable, '-m', 'pip', 'download', '--dest', str(BUILD / 'wheels'),
                    '--platform', 'win_amd64', '--python-version', '313', '--implementation', 'cp',
                    '--abi', 'cp313', '--only-binary=:all:', *requirements], check=True)
    site = PAYLOAD / 'python' / 'Lib' / 'site-packages'
    manifest['wheels'] = {}
    for wheel in sorted((BUILD / 'wheels').glob('*.whl')):
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(site)
        manifest['wheels'][wheel.name] = hashlib.sha256(wheel.read_bytes()).hexdigest()
    for data in site.glob('*.data'):
        for kind in ('purelib', 'platlib'):
            if (data / kind).exists():
                shutil.copytree(data / kind, site, dirs_exist_ok=True)
    shutil.copytree(ROOT.parent / 'app', PAYLOAD / 'app', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    # Only editorial fonts, never uploaded documents or generated previews.
    fonts = PAYLOAD / 'storage' / 'fonts'
    fonts.mkdir(parents=True, exist_ok=True)
    for source in (ROOT.parent / 'storage' / 'fonts').glob('*'):
        if source.is_file() and source.suffix.lower() in {'.otf', '.ttf', '.json'}:
            shutil.copy2(source, fonts / source.name)
    shutil.copy2(ROOT / 'desktop.py', PAYLOAD / 'desktop.py')
    subprocess.run(['docker', 'cp', 'languagetool-vkv:/LanguageTool/.', str(PAYLOAD / 'languagetool')], check=True)
    for name in ('config.properties', 'start.sh'):
        (PAYLOAD / 'languagetool' / name).unlink(missing_ok=True)
    manifest['languagetool_container_image'] = subprocess.check_output(
        ['docker', 'inspect', 'languagetool-vkv', '--format', '{{.Image}}'], text=True).strip()
    (PAYLOAD / 'build-manifest.json').write_text(json.dumps(manifest, indent=2))
    shutil.copy2(ROOT / 'GEBRUIK.txt', PAYLOAD / 'GEBRUIK.txt')
    env = dict(os.environ, NSISDIR=str(BUILD / 'nsis'))
    for script in ('launcher.nsi', 'setup.nsi'):
        subprocess.run([str(BUILD / 'makensis'), '-V2', script], cwd=ROOT, env=env, check=True)
    print(ROOT / 'dist' / 'VKV-Documentcontrole-Setup.exe', flush=True)


if __name__ == '__main__':
    main()
