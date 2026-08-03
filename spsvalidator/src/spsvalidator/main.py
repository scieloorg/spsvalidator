from __future__ import annotations

import argparse
import locale
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import webview
from werkzeug.serving import make_server

from spsvalidator.app import create_app
from spsvalidator.desktop_api import DesktopApi
from spsvalidator.version import APP_DISPLAY_NAME


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _show_error_dialog(title: str, message: str) -> None:
    try:
        import tkinter
        from tkinter import messagebox
    except ImportError:
        print(message, file=sys.stderr)
        return
    root = tkinter.Tk()
    root.withdraw()
    messagebox.showerror(title, message)
    root.destroy()


def _bind_server(app, host: str, port: int):
    # werkzeug.serving.make_server trata EADDRINUSE internamente chamando
    # sys.exit(1) após só um print em stderr (invisível no executável
    # --windowed); testamos o bind nós mesmos antes para poder mostrar um
    # diálogo nativo em vez de deixar o processo morrer em silêncio.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, port))
    except OSError as exc:
        _show_error_dialog(
            APP_DISPLAY_NAME,
            f"Não foi possível iniciar o servidor em {host}:{port}.\n"
            f"{exc.strerror or exc}\n\n"
            "Escolha outra porta com --port ou libere a porta em uso.",
        )
        sys.exit(1)
    return make_server(host, port, app, threaded=True)


def main() -> None:
    parser = argparse.ArgumentParser(prog="spsvalidator")
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    if args.browser:
        app = create_app(execution_mode="browser")
        host = args.host
        port = args.port or _free_port()
        server = _bind_server(app, host, port)
        url = f"http://{host}:{port}"
        app.config["SERVER_URL"] = url
        app.config["SERVER"] = server
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
        server.serve_forever()
        return

    system_language = locale.getlocale()[0]
    app = create_app(execution_mode="desktop", system_language=system_language)

    db_path = app.config["DB_PATH"]
    host = args.host
    port = args.port or _free_port()
    server = _bind_server(app, host, port)
    app.config["SERVER"] = server
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.4)
    icon_path = Path(__file__).resolve().parent / "web" / "static" / "img" / "icon.png"
    window_kwargs = {
        "title": APP_DISPLAY_NAME,
        "url": f"http://{host}:{port}",
        "width": 1360,
        "height": 900,
    }
    window_kwargs["js_api"] = DesktopApi(db_path)
    webview.create_window(**window_kwargs)
    webview.start(
        private_mode=False,
        storage_path=str(Path(db_path).parent / "webview_data"),
        icon=str(icon_path) if icon_path.is_file() else None,
    )
    # webview.start() só retorna depois que a janela nativa é fechada; o
    # encerramento explícito e a espera pelo fim do servidor ficam aqui,
    # não em um hook de evento, porque essa é a única janela do app.
    server.shutdown()
    thread.join()


if __name__ == "__main__":
    main()
