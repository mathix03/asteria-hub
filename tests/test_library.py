import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from app import create_app
from library import Library


@pytest.fixture
def library(tmp_path):
    return Library(tmp_path / 'profile')


def populate(library, tmp_path):
    roms = tmp_path / 'roms'
    roms.mkdir()
    (roms / 'Pokémon [0100000000000000].NSP').write_bytes(b'test')
    sub = roms / 'sub'
    sub.mkdir()
    (sub / 'Homebrew & test.nro').write_bytes(b'homebrew')
    (roms / 'ignored.txt').write_text('no')
    library.configure('', [str(roms), str(sub)])
    return roms


def test_scan_search_favorites_and_dedup(library, tmp_path):
    populate(library, tmp_path)
    assert len(library.games) == 2
    game = library.list_games('pokemon')[0]
    assert library.list_games('pokemon', format='XCI') == []
    library.favorite(game['id'], True)
    assert len(library.list_games(favorites=True)) == 1
    assert Library(library.directory).list_games(favorites=True)[0]['id'] == game['id']
    library.favorite(game['id'], False)
    assert library.list_games(favorites=True) == []


def test_missing_file_not_launched(library, tmp_path):
    roms = populate(library, tmp_path)
    emulator = tmp_path / 'eden.exe'
    emulator.write_bytes(b'placeholder')
    library.configure(str(emulator), [str(roms)])
    game = library.list_games('pokemon')[0]
    Path(game['path']).unlink()
    with patch('library.subprocess.Popen') as popen, pytest.raises(ValueError):
        library.launch(game['id'])
    popen.assert_not_called()


def test_launch_and_history(library, tmp_path):
    roms = populate(library, tmp_path)
    emulator = tmp_path / 'eden.exe'
    emulator.write_bytes(b'placeholder')
    library.configure(str(emulator), [str(roms)])
    game = library.games[0]
    with patch('library.subprocess.Popen') as popen:
        library.launch(game['id'])
        assert popen.call_args.args[0] == [str(emulator), game['path']]
    assert library.list_games(sort='recent')[0]['count'] == 1
    assert len(library.list_games(played=True)) == 1
    assert Library(library.directory).settings['history'][game['id']]['count'] == 1


def test_invalid_configuration_preserves_settings(library, tmp_path):
    populate(library, tmp_path)
    old = json.loads(library.path.read_text())
    with pytest.raises(ValueError):
        library.configure('', [str(tmp_path / 'missing')])
    assert json.loads(library.path.read_text()) == old


@pytest.mark.parametrize('bad', ['{broken', '[]', '{"favorites":42}', '{"rom_directories":[7]}', '{"history":{"x":{"count":"bad"}}}'])
def test_corrupted_settings_backed_up(tmp_path, bad):
    (tmp_path / 'settings.json').write_text(bad)
    service = Library(tmp_path)
    assert service.warning
    assert next(tmp_path.glob('settings.invalid.*.json')).read_text() == bad


def test_api_boundaries(tmp_path):
    with TestClient(create_app(tmp_path / 'profile')) as client:
        token = client.get('/api/session').json()['token']
        headers = {'x-asteria-token': token}
        assert client.get('/api/health').json()['application'] == 'asteria-hub'
        assert client.post('/api/scan').status_code == 403
        assert client.post('/api/scan', headers={**headers, 'origin': 'https://evil.example'}).status_code == 403
        assert client.post('/api/scan', headers={**headers, 'origin': 'http://testserver'}).status_code == 200
        assert client.get('/api/status', headers={'host': 'evil.example'}).status_code == 400
        assert client.get('/api/games?page=0').status_code == 422
        assert client.get('/api/games?limit=10000').status_code == 422
        assert client.get('/api/games?sort=invalid').status_code == 422
        assert client.post('/api/games/unknown/launch', headers=headers).status_code == 404
        assert client.post('/api/settings', json={'rom_directories': ['/nonexistent-path-asteria']}, headers=headers).status_code == 400
        assert client.get('/').status_code == 200
        assert "script-src 'self'" in client.get('/').headers['content-security-policy']


def test_api_pagination_export_and_favorites(tmp_path):
    app = create_app(tmp_path / 'profile')
    populate(app.state.library, tmp_path)
    with TestClient(app) as client:
        headers = {'x-asteria-token': client.get('/api/session').json()['token']}
        data = client.get('/api/games?limit=1&page=999').json()
        assert data['page'] == data['pages'] == 2
        game = data['games'][0]
        assert client.post(f"/api/games/{game['id']}/favorite", json={'enabled': True}, headers=headers).status_code == 200
        assert client.get('/api/games?favorites=true').json()['total'] == 1
        exported = client.get('/api/export')
        assert 'attachment' in exported.headers['content-disposition']
        assert all('path' not in g for g in exported.json()['games'])
        assert client.get('/api/games?q=nom-absent').json()['games'] == []


def test_local_cover_and_unknown_id(tmp_path):
    app = create_app(tmp_path / 'profile')
    roms = populate(app.state.library, tmp_path)
    game = app.state.library.list_games('pokemon')[0]
    cover = Path(game['path']).with_suffix('.png')
    cover.write_bytes(b'local cover fixture')
    app.state.library.scan()
    assert app.state.library.list_games('pokemon')[0]['has_cover']
    with TestClient(app) as client:
        result = client.get(f"/api/games/{game['id']}/cover")
        assert result.status_code == 200
        assert result.content == cover.read_bytes()
        assert result.headers['content-type'] == 'image/png'
        assert client.get('/api/games/unknown/cover').status_code == 404
        other = app.state.library.list_games(format='NRO')[0]
        assert client.get(f"/api/games/{other['id']}/cover").status_code == 404


def test_disconnected_directory_warning(library, tmp_path):
    missing = tmp_path / 'offline'
    library.save({'rom_directories': [str(missing)]})
    library.scan()
    assert library.games == []
    assert library.snapshot()['warnings']


def test_write_failure_does_not_change_settings(library, tmp_path):
    populate(library, tmp_path)
    original = json.loads(library.path.read_text())
    with patch('library.os.replace', side_effect=PermissionError('Disk unavailable')):
        with pytest.raises(PermissionError):
            library.save({'favorites': ['new']})
    assert library.settings == original
    assert json.loads(library.path.read_text()) == original


def test_real_process_handoff_with_spaces(library, tmp_path):
    directory = tmp_path / 'folder with spaces'
    directory.mkdir()
    marker = tmp_path / 'process-received-argument.txt'
    script = directory / 'Synthetic launch fixture.nro'
    script.write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("ok")\n', encoding='utf-8')
    library.configure(sys.executable, [str(directory)])
    library.launch(library.games[0]['id'])
    for _ in range(100):
        if marker.exists():
            break
        time.sleep(.05)
    assert marker.read_text() == 'ok'
