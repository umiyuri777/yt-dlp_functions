import json
import importlib.util
import logging
import mimetypes
import os
import re
import shutil
import tempfile
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

_handler_path = Path(__file__).with_name("lambda") / "handler.py"
_handler_spec = importlib.util.spec_from_file_location("download_handler", _handler_path)
if _handler_spec is None or _handler_spec.loader is None:
    raise RuntimeError("Could not load download handler")
_handler = importlib.util.module_from_spec(_handler_spec)
_handler_spec.loader.exec_module(_handler)

ALLOWED_EXTENSIONS = _handler.ALLOWED_EXTENSIONS
DEFAULT_AUDIO_EXTENSION = _handler.DEFAULT_AUDIO_EXTENSION
QUALITY_HEIGHT_MAP = _handler.QUALITY_HEIGHT_MAP
_download_media = _handler._download_media
_normalize_extension = _handler._normalize_extension
_sanitize_filename = _handler._sanitize_filename

logger = logging.getLogger("yt-dlp-local")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", "/downloads"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8080").rstrip("/")
MAX_CONTENT_LENGTH = 16 * 1024
FILE_ID_PATTERN = re.compile(r"^[0-9a-f-]{36}\.[a-z0-9]+$")


def _json_response(handler: BaseHTTPRequestHandler, status: int, body: dict) -> None:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(payload)


class DownloadHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/health":
            _json_response(self, HTTPStatus.OK, {"status": "ok"})
            return

        prefix = "/files/"
        if not self.path.startswith(prefix):
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return

        file_id = unquote(self.path[len(prefix):])
        if not FILE_ID_PATTERN.fullmatch(file_id):
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "File not found"})
            return
        file_path = DOWNLOAD_DIR / file_id
        if not file_path.is_file():
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "File not found"})
            return

        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type", mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        )
        self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
        self.send_header("Content-Length", str(file_path.stat().st_size))
        self.end_headers()
        with file_path.open("rb") as source:
            shutil.copyfileobj(source, self.wfile)

    def do_POST(self) -> None:
        if self.path != "/download":
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_CONTENT_LENGTH:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid request size"})
            return
        try:
            body = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON body"})
            return
        if not isinstance(body, dict):
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "JSON object required"})
            return

        url = str(body.get("url") or "").strip()
        if not re.match(r"^https?://", url, re.IGNORECASE):
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "A valid HTTP(S) URL is required"})
            return
        try:
            extension = _normalize_extension(body.get("extension") or DEFAULT_AUDIO_EXTENSION)
        except ValueError as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        requested_name = _sanitize_filename(str(body.get("filename") or ""))
        if body.get("filename") and not requested_name:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid filename"})
            return
        quality = str(body.get("quality") or "720").lower()
        if extension not in {"mp3", "m4a", "wav", "opus", "flac", "aac"} and quality not in QUALITY_HEIGHT_MAP:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid quality"})
            return

        work_dir = Path(tempfile.mkdtemp(prefix="yt-dlp-"))
        try:
            local_file = _download_media(url, work_dir, extension, quality, requested_name or None)
            file_id = f"{uuid.uuid4()}{local_file.suffix.lower()}"
            output = DOWNLOAD_DIR / file_id
            shutil.move(str(local_file), output)
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "filename": requested_name + output.suffix if requested_name else output.name,
                    "download_url": f"{PUBLIC_BASE_URL}/files/{file_id}",
                },
            )
        except Exception as exc:
            logger.exception("Download failed")
            _json_response(self, HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def log_message(self, format: str, *args: object) -> None:
        logger.info("%s - %s", self.address_string(), format % args)


def main() -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer((host, port), DownloadHandler)
    logger.info("Listening on %s:%s", host, port)
    server.serve_forever()


if __name__ == "__main__":
    main()
