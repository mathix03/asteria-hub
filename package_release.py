"""Package tracked sources and a Windows binary with dependency license texts."""
import hashlib
from importlib.metadata import distribution
from pathlib import Path
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from app import VERSION


def main():
    root = Path(__file__).resolve().parent
    output = root / 'dist'
    binary = output / 'AsteriaHub.exe'
    if not binary.is_file():
        raise SystemExit('Run python build.py on Windows first.')
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    forbidden = {'.keys', '.nsp', '.nsz', '.xci', '.nro', '.exe', '.zip'}
    source = output / f'AsteriaHub-{VERSION}-source.zip'
    with ZipFile(source, 'w', ZIP_DEFLATED) as archive:
        for name in filter(None, paths):
            path = root / name
            if path.suffix.lower() in forbidden or not path.resolve().is_relative_to(root):
                raise ValueError('Private or external file must not be tracked: ' + name)
            archive.write(path, f'AsteriaHub-{VERSION}/' + name)
    release = output / f'AsteriaHub-{VERSION}-Windows.zip'
    with ZipFile(release, 'w', ZIP_DEFLATED) as archive:
        archive.write(binary, binary.name)
        for name in ['README.md', 'README.en.md', 'CHANGELOG.md', 'CONTRIBUTING.md', 'LICENSE']:
            archive.write(root / name, name)
        for path in (root / 'docs').iterdir():
            if path.suffix.lower() in {'.png', '.svg'}:
                archive.write(path, 'docs/' + path.name)
        names = [line.split('==')[0] for line in (root / 'requirements.lock').read_text().splitlines()
                 if line and not line.startswith('#')] + ['pyinstaller']
        for name in names:
            package = distribution(name)
            collected = 0
            for relative in package.files or []:
                lower = str(relative).lower().replace('\\', '/')
                basename = Path(lower).name
                if '/licenses/' in lower or basename.startswith(('license', 'copying', 'notice', 'copyright')):
                    path = Path(package.locate_file(relative))
                    if path.is_file():
                        archive.write(path, 'third-party-licenses/' + name + '/' + str(relative).replace('\\', '/'))
                        collected += 1
            if not collected:
                raise RuntimeError('No license text found for ' + name)
        python_license = Path(sys.base_prefix) / 'LICENSE.txt'
        if not python_license.is_file():
            raise RuntimeError('Python LICENSE.txt missing from build environment.')
        archive.write(python_license, 'third-party-licenses/Python-LICENSE.txt')
    artifacts = [binary, source, release]
    checksums = ''.join(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n' for path in artifacts)
    (output / 'SHA256SUMS.txt').write_text(checksums, encoding='utf-8')
    print('Release packages ready. Tracked files only; dependency license texts included.')
    print(checksums)


if __name__ == '__main__':
    main()
