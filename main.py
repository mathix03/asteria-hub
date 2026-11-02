"""Run with python main.py; no import-time launch or automatic shutdown."""
import argparse
import socket
import threading
import time
import webbrowser

import uvicorn
from app import create_app


def main():
    parser = argparse.ArgumentParser(description='Asteria Hub — bibliothèque locale')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Le port doit être compris entre 1 et 65535.')
    # Bind before opening a browser: never open an unrelated service on an occupied port.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', args.port))
    except OSError:
        sock.close()
        parser.exit(1, 'Port occupé. Utilise --port 8766 ou ferme l’autre instance.\n')
    url = f'http://127.0.0.1:{args.port}'
    server = uvicorn.Server(uvicorn.Config(create_app(), host='127.0.0.1', port=args.port, log_level='info'))
    if not args.no_browser:
        def open_when_ready():
            for _ in range(150):
                if server.started:
                    webbrowser.open(url)
                    return
                if server.should_exit:
                    return
                time.sleep(.1)
        threading.Thread(target=open_when_ready, daemon=True).start()
    print(f'Asteria Hub : {url}\nFerme cette fenêtre ou utilise Ctrl+C pour arrêter.')
    try:
        server.run(sockets=[sock])
    finally:
        sock.close()


if __name__ == '__main__':
    main()
