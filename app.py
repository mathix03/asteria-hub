"""Loopback-only API for Asteria Hub."""
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from library import Library

VERSION = '2.0.0'
STATIC = Path(__file__).resolve().parent / 'static'


class Settings(BaseModel):
    emulator_path: str = Field(default='', max_length=4096)
    rom_directories: list[str] = Field(default_factory=list, max_length=100)


class Favorite(BaseModel):
    enabled: bool


def create_app(directory=None):
    app = FastAPI(title='Asteria Hub', version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)
    library = Library(directory)
    app.state.library = library
    token = secrets.token_urlsafe(32)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])

    @app.middleware('http')
    async def local_access(request: Request, call_next):
        if request.url.path.startswith('/api/') and request.method not in ('GET', 'HEAD'):
            origin = request.headers.get('origin')
            if origin and origin != str(request.base_url).rstrip('/'):
                return JSONResponse({'detail': 'Origine refusée.'}, status_code=403)
            if not secrets.compare_digest(request.headers.get('x-asteria-token', ''), token):
                return JSONResponse({'detail': 'Session expirée. Recharge la page.'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith('/api/') else 'no-cache'
        return response

    @app.exception_handler(ValueError)
    async def invalid_value(request, error):
        return JSONResponse({'detail': str(error)}, status_code=400)

    @app.exception_handler(KeyError)
    async def missing_game(request, error):
        return JSONResponse({'detail': error.args[0]}, status_code=404)

    @app.exception_handler(OSError)
    async def disk_error(request, error):
        return JSONResponse({'detail': 'Opération impossible : ' + str(error)}, status_code=400)

    @app.get('/')
    def index():
        return FileResponse(STATIC / 'index.html')

    @app.get('/api/health')
    def health():
        return {'application': 'asteria-hub', 'version': VERSION}

    @app.get('/api/session')
    def session():
        return {'token': token}

    @app.get('/api/status')
    def status():
        return library.snapshot()

    @app.get('/api/games')
    def games(q: str = Query('', max_length=500), favorites: bool = False, played: bool = False,
              format: str = Query('all', pattern='^(all|NSP|XCI|NSZ|NRO)$'),
              sort: str = Query('title', pattern='^(title|size|recent|modified)$'),
              page: int = Query(1, ge=1), limit: int = Query(48, ge=1, le=200)):
        items = library.list_games(q, favorites, format, sort, played)
        pages = max(1, (len(items) + limit - 1) // limit)
        page = min(page, pages)
        return {'games': items[(page-1)*limit:page*limit], 'total': len(items), 'page': page, 'pages': pages}

    @app.post('/api/settings')
    def settings(value: Settings):
        library.configure(value.emulator_path, value.rom_directories)
        return library.snapshot()

    @app.post('/api/scan')
    def scan():
        library.scan()
        return library.snapshot()

    @app.post('/api/games/{game_id}/favorite')
    def favorite(game_id: str, value: Favorite):
        library.favorite(game_id, value.enabled)
        return {'success': True}

    @app.get('/api/games/{game_id}/cover')
    def cover(game_id: str):
        path = library.cover(game_id)
        if path is None:
            raise HTTPException(404, 'Aucune jaquette locale.')
        return FileResponse(path)

    @app.post('/api/games/{game_id}/launch')
    def launch(game_id: str):
        library.launch(game_id)
        return {'success': True}

    @app.get('/api/export')
    def export():
        return JSONResponse({'application': 'Asteria Hub', 'version': VERSION,
                             'games': [{k: v for k, v in g.items() if k != 'path'} for g in library.list_games()]},
                            headers={'Content-Disposition': 'attachment; filename="asteria-library.json"'})

    app.mount('/static', StaticFiles(directory=STATIC), name='static')
    return app
