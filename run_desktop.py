import socket
import threading
import time
from pathlib import Path
import sys
import traceback

import requests
import uvicorn
import webview

from app.main import create_app


BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000


def _get_runtime_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


class DesktopApi:
    def save_translated_pdf(self, job_id: str) -> None:
        from tkinter import Tk
        from tkinter.filedialog import asksaveasfilename

        backend_url = f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/jobs/{job_id}/download"

        response = requests.get(backend_url, timeout=60)
        response.raise_for_status()

        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        save_path = asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            title="Save translated PDF",
        )

        root.destroy()

        if not save_path:
            return

        path_obj = Path(save_path)
        path_obj.write_bytes(response.content)


def start_server() -> None:
    log_path = _get_runtime_dir() / "desktop-server.log"

    try:
        app = create_app()
        config = uvicorn.Config(
            app,
            host=BACKEND_HOST,
            port=BACKEND_PORT,
            log_level="info",
        )
        server = uvicorn.Server(config)
        server.run()
    except Exception:
        try:
            log_path.write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        raise


def main() -> None:
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    max_attempts = 50
    attempt = 0
    while attempt < max_attempts:
        try:
            with socket.create_connection((BACKEND_HOST, BACKEND_PORT), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
            attempt += 1

    api = DesktopApi()
    webview.create_window(
        "PDF Translator",
        f"http://{BACKEND_HOST}:{BACKEND_PORT}",
        width=1200,
        height=800,
        resizable=True,
        js_api=api,
    )
    webview.start()


if __name__ == "__main__":
    main()
