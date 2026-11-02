"""End-to-end test using a real server, isolated profile and synthetic files."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='asteria-e2e-') as temporary:
        work = Path(temporary)
        roms = work / 'games'
        roms.mkdir()
        for name in ['Pokémon Adventure.nsp', 'Homebrew & friends.nro'] + [f'Adventure {i:02}.xci' for i in range(53)]:
            (roms / name).write_bytes(b'synthetic test fixture, not a game')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        env = {**os.environ, 'ASTERIA_DATA_DIR': str(work / 'profile'), 'PYTHONUTF8': '1'}
        log = open(work / 'server.log', 'w', encoding='utf-8')
        executable = os.environ.get('ASTERIA_EXECUTABLE')
        command = [str(Path(executable).resolve())] if executable else [sys.executable, str(ROOT / 'main.py')]
        process = subprocess.Popen(command + ['--no-browser', '--port', str(port)],
                                   cwd=ROOT, env=env, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(url + '/api/health', timeout=.5):
                        break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError((work / 'server.log').read_text())
                    time.sleep(.1)
            else:
                raise RuntimeError('Server startup timed out')
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url)
                expect(page.get_by_text('Votre prochaine aventure commence ici')).to_be_visible()
                page.locator('#configureBtn').click()
                page.locator('#directories').fill(str(work / 'missing'))
                page.locator('#saveSettings').click()
                expect(page.locator('#settingsError')).to_contain_text('Dossier introuvable')
                expect(page.locator('#settingsDialog')).to_be_visible()
                page.locator('#directories').fill(str(roms))
                page.locator('#saveSettings').click()
                expect(page.locator('#settingsDialog')).not_to_be_visible()
                expect(page.locator('#gameCount')).to_have_text('55')
                expect(page.locator('.card')).to_have_count(48)
                page.locator('#next').click()
                expect(page.locator('.card')).to_have_count(7)
                page.locator('#search').fill('pokemon')
                expect(page.locator('.card')).to_have_count(1)
                expect(page.locator('.card h3')).to_have_text('Pokémon Adventure')
                page.locator('.favorite').click()
                expect(page.locator('.favorite')).to_have_attribute('aria-pressed', 'true')
                page.locator('.play').click()
                expect(page.locator('#toast')).to_contain_text('Configure un émulateur')
                page.reload()
                expect(page.locator('#gameCount')).to_have_text('55')
                page.locator('#favoritesTab').click()
                expect(page.locator('.card')).to_have_count(1)
                page.locator('.favorite').click()
                expect(page.locator('.card')).to_have_count(0)
                page.locator('#recentTab').click()
                expect(page.locator('.card')).to_have_count(0)
                page.locator('#allTab').click()
                page.locator('#format').select_option('NRO')
                expect(page.locator('.card')).to_have_count(1)
                page.locator('#search').fill('<script>')
                expect(page.locator('.card')).to_have_count(0)
                assert page.locator('script').count() == 1
                page.locator('#search').fill('')
                page.locator('#format').select_option('all')
                expect(page.locator('.card')).to_have_count(48)
                page.locator('#scanBtn').click()
                expect(page.locator('#scanBtn')).to_be_enabled()
                with page.expect_download() as download:
                    page.locator('#exportBtn').click()
                data = json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
                assert len(data['games']) == 55
                assert all('path' not in game for game in data['games'])
                output = Path(os.environ.get('ASTERIA_SCREENSHOTS', ROOT / 'test-results'))
                output.mkdir(parents=True, exist_ok=True)
                page.locator('#toast').evaluate('(node) => node.hidden = true')
                page.screenshot(path=str(output / 'asteria-desktop.png'))
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
                page.screenshot(path=str(output / 'asteria-mobile.png'))
                page.locator('#settingsBtn').click()
                expect(page.locator('#settingsDialog')).to_be_visible()
                page.keyboard.press('Escape')
                expect(page.locator('#settingsDialog')).not_to_be_visible()
                assert errors == [], errors
                browser.close()
                print('Browser smoke passed: configuration, validation, scan, pagination, search, favorites, persistence, export, mobile, dialogs; no JavaScript errors.')
        finally:
            if sys.platform == 'win32' and process.poll() is None:
                # PyInstaller onefile has a bootloader parent and application child.
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW, check=False)
            elif process.poll() is None:
                process.terminate()
            process.wait(timeout=15)
            log.close()


if __name__ == '__main__':
    main()
