"""Reproducible application build; never bundles user data or third-party binaries."""
import os
from pathlib import Path
import subprocess
import sys


def main():
    base = Path(__file__).resolve().parent
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--onefile', '--clean',
                    '--name=AsteriaHub', '--add-data=' + str(base / 'static') + os.pathsep + 'static',
                    '--collect-all=uvicorn', str(base / 'main.py')], cwd=base, check=True)
    print('Build complete: ' + str(base / 'dist'))


if __name__ == '__main__':
    main()
