"""Portable local library. No network access or installation on startup."""
import hashlib
import json
import os
import subprocess
import sys
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

EXTENSIONS = {'.nsp', '.xci', '.nsz', '.nro'}


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.casefold())
                   if unicodedata.category(c) != 'Mn')


def data_directory():
    override = os.environ.get('ASTERIA_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == 'win32':
        return Path(os.environ.get('APPDATA', Path.home())) / 'AsteriaHub'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'AsteriaHub'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'asteria-hub'


class Library:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else data_directory()
        self.directory.mkdir(parents=True, exist_ok=True)
        # Resolve Windows redirected/virtualized AppData before atomic renames.
        # A logical C: path can actually be backed by another volume.
        self.directory = self.directory.resolve()
        self.lock = threading.RLock()
        self.scan_lock = threading.Lock()
        self.path = self.directory / 'settings.json'
        self.settings = {'emulator_path': '', 'rom_directories': [], 'favorites': [], 'history': {}}
        self.warning = ''
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(saved, dict):
                    raise ValueError('Expected an object')
                for key, default in self.settings.items():
                    if not isinstance(saved.get(key, default), type(default)):
                        raise ValueError('Invalid settings')
                if not all(isinstance(x, str) for x in saved.get('rom_directories', []) + saved.get('favorites', [])):
                    raise ValueError('Invalid settings entries')
                if not all(isinstance(v, dict) and isinstance(v.get('count', 0), int) and
                           isinstance(v.get('last_played', ''), str) for v in saved.get('history', {}).values()):
                    raise ValueError('Invalid history')
                self.settings.update({k: saved[k] for k in self.settings if k in saved})
            except (OSError, ValueError, TypeError):
                backup = self.path.with_name('settings.invalid.' + datetime.now().strftime('%Y%m%d%H%M%S%f') + '.json')
                self.path.replace(backup)
                self.warning = 'Préférences illisibles : copie conservée dans ' + backup.name
        self.games = []
        self.scan()

    def save(self, changes):
        with self.lock:
            updated = {**self.settings, **changes}
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temporary, self.path)
            self.settings = updated

    def configure(self, emulator_path, rom_directories):
        emulator = str(Path(emulator_path).expanduser().resolve()) if emulator_path.strip() else ''
        if emulator and not Path(emulator).is_file():
            raise ValueError("L’exécutable de l’émulateur est introuvable.")
        if emulator and sys.platform == 'win32' and Path(emulator).suffix.lower() != '.exe':
            raise ValueError('Sélectionne un exécutable .exe.')
        directories = []
        for value in rom_directories:
            if not value.strip():
                continue
            path = Path(value).expanduser().resolve()
            if not path.is_dir():
                raise ValueError('Dossier introuvable : ' + str(path))
            if str(path) not in directories:
                directories.append(str(path))
        self.save({'emulator_path': emulator, 'rom_directories': directories})
        return self.scan()

    def scan(self):
        with self.scan_lock:
            with self.lock:
                directories = list(self.settings['rom_directories'])
            found = {}
            warnings = []
            for directory in directories:
                if not Path(directory).is_dir():
                    warnings.append('Dossier indisponible : ' + directory)
                    continue
                def on_error(error):
                    warnings.append(str(error))
                for root, dirs, files in os.walk(directory, followlinks=False, onerror=on_error):
                    dirs[:] = sorted(d for d in dirs if not Path(root, d).is_symlink())
                    for filename in sorted(files):
                        path = Path(root, filename)
                        if path.suffix.lower() not in EXTENSIONS or path.is_symlink():
                            continue
                        try:
                            path = path.resolve()
                            key = os.path.normcase(str(path))
                            stat = path.stat()
                            game_id = hashlib.sha256(key.encode()).hexdigest()[:24]
                            has_cover = any(path.with_suffix(ext).is_file() and not path.with_suffix(ext).is_symlink()
                                            for ext in ('.png', '.jpg', '.jpeg', '.webp'))
                            found[key] = {'id': game_id, 'title': path.stem, 'path': str(path), 'has_cover': has_cover,
                                          'format': path.suffix[1:].upper(), 'size': stat.st_size,
                                          'modified': stat.st_mtime}
                        except OSError as error:
                            warnings.append(str(error))
            with self.lock:
                self.games = sorted(found.values(), key=lambda g: normalize(g['title']))
                self.scan_warnings = warnings
            return len(found)

    def list_games(self, query='', favorites=False, format='all', sort='title', played=False):
        with self.lock:
            results = [{**g, 'favorite': g['id'] in self.settings['favorites'],
                        **self.settings['history'].get(g['id'], {})} for g in self.games]
        terms = normalize(query).split()
        results = [g for g in results if all(t in normalize(g['title']) for t in terms)
                   and (not favorites or g['favorite']) and (format == 'all' or g['format'] == format)
                   and (not played or g.get('count', 0) > 0)]
        if sort == 'size':
            results.sort(key=lambda g: (-g['size'], normalize(g['title'])))
        elif sort == 'recent':
            results.sort(key=lambda g: (g.get('last_played', ''), g['title']), reverse=True)
        elif sort == 'modified':
            results.sort(key=lambda g: g['modified'], reverse=True)
        return results

    def game(self, game_id):
        with self.lock:
            game = next((g for g in self.games if g['id'] == game_id), None)
            if not game:
                raise KeyError('Jeu introuvable. Relance le scan.')
            return dict(game)

    def favorite(self, game_id, enabled):
        self.game(game_id)
        with self.lock:
            favorites = set(self.settings['favorites'])
            favorites.add(game_id) if enabled else favorites.discard(game_id)
            self.save({'favorites': sorted(favorites)})

    def cover(self, game_id):
        path = Path(self.game(game_id)['path'])
        for extension in ('.png', '.jpg', '.jpeg', '.webp'):
            candidate = path.with_suffix(extension)
            if candidate.is_file() and not candidate.is_symlink():
                return candidate
        return None

    def launch(self, game_id):
        game = self.game(game_id)
        emulator = self.settings['emulator_path']
        if not emulator or not Path(emulator).is_file():
            raise ValueError('Configure un émulateur valide dans les paramètres.')
        if not Path(game['path']).is_file():
            raise ValueError('Ce fichier a été déplacé ou supprimé. Relance le scan.')
        subprocess.Popen([emulator, game['path']], cwd=str(Path(emulator).parent),
                         creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        with self.lock:
            history = dict(self.settings['history'])
            history[game_id] = {'count': history.get(game_id, {}).get('count', 0) + 1,
                                'last_played': datetime.now(timezone.utc).isoformat()}
            self.save({'history': history})

    def snapshot(self):
        with self.lock:
            return {'settings': json.loads(json.dumps(self.settings)), 'count': len(self.games),
                    'total_size': sum(g['size'] for g in self.games),
                    'emulator_ready': bool(self.settings['emulator_path'] and Path(self.settings['emulator_path']).is_file()),
                    'warnings': ([self.warning] if self.warning else []) + self.scan_warnings}
