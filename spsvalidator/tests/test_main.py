import socket
import threading
import time
import urllib.request

import pytest

from spsvalidator.app import create_app
from spsvalidator.main import _bind_server, _free_port


def test_free_port_returns_an_available_port():
    port = _free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", port))


def test_bind_server_serves_concurrent_requests(tmp_path):
    """Regressão da issue #39: wsgiref.simple_server não é threaded e uma
    requisição lenta bloqueava todas as outras até ela terminar."""
    app = create_app(str(tmp_path), execution_mode="browser")

    @app.route("/slow")
    def slow():
        time.sleep(0.5)
        return "ok"

    server = _bind_server(app, "127.0.0.1", 0)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)

    try:
        results = {}

        def fetch(key, path):
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}{path}", timeout=3
            ) as response:
                results[key] = response.status

        slow_thread = threading.Thread(target=fetch, args=("slow", "/slow"))
        fast_thread = threading.Thread(target=fetch, args=("fast", "/"))

        slow_thread.start()
        time.sleep(0.05)  # garante que /slow começou a ser atendida primeiro
        t0 = time.time()
        fast_thread.start()
        fast_thread.join(timeout=3)
        fast_elapsed = time.time() - t0
        slow_thread.join(timeout=3)

        assert results.get("fast") == 200
        assert results.get("slow") == 200
        # Servidor síncrono só responderia "/" depois de "/slow" terminar
        # (>= 0.5s); com threaded=True a resposta chega bem antes disso.
        assert fast_elapsed < 0.4
    finally:
        server.shutdown()
        thread.join(timeout=3)


def test_bind_server_port_in_use_shows_dialog_and_exits(tmp_path, monkeypatch):
    occupier = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupier.bind(("127.0.0.1", 0))
    occupier.listen(1)
    port = occupier.getsockname()[1]

    calls = []
    monkeypatch.setattr(
        "spsvalidator.main._show_error_dialog",
        lambda title, message: calls.append((title, message)),
    )

    app = create_app(str(tmp_path), execution_mode="browser")
    try:
        with pytest.raises(SystemExit) as exc_info:
            _bind_server(app, "127.0.0.1", port)
        assert exc_info.value.code == 1
        assert len(calls) == 1
        assert str(port) in calls[0][1]
    finally:
        occupier.close()


def test_server_shutdown_stops_serve_forever_thread(tmp_path):
    app = create_app(str(tmp_path), execution_mode="browser")
    server = _bind_server(app, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    assert thread.is_alive()

    server.shutdown()
    thread.join(timeout=3)

    assert not thread.is_alive()