import json
import logging
import os
import re
import shutil
import uuid
from pathlib import Path

import boto3
import yt_dlp

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BUCKET_NAME = os.environ.get("BUCKET_NAME")
PRESIGNED_EXPIRY = int(os.environ.get("PRESIGNED_EXPIRY", "3600"))
TMP_DIR = Path("/tmp")

AUDIO_EXTENSIONS = {"mp3", "m4a", "wav", "opus", "flac", "aac"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mkv", "avi", "mov"}
DEFAULT_AUDIO_EXTENSION = "m4a"
DEFAULT_VIDEO_EXTENSION = "mp4"
ALLOWED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

QUALITY_HEIGHT_MAP = {
    "360": 360,
    "480": 480,
    "720": 720,
    "1080": 1080,
    "best": None,
}

CONTENT_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".opus": "audio/opus",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
}

s3_client = boto3.client("s3") if BUCKET_NAME else None

CORS_HEADERS = {
    "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOW_ORIGIN", "*"),
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _parse_body(event: dict) -> dict:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    return json.loads(raw) if isinstance(raw, str) else raw


def _sanitize_filename(name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", (name or "").strip())
    return sanitized[:200]


def _normalize_extension(extension: str | None) -> str:
    ext = (extension or DEFAULT_AUDIO_EXTENSION).strip().lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported extension: {ext}. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    return ext


def _is_audio_extension(ext: str) -> bool:
    return ext in AUDIO_EXTENSIONS


def _video_format_selector(quality: str | None) -> str:
    height = QUALITY_HEIGHT_MAP.get((quality or "720").lower())
    if height is None:
        return "bestvideo+bestaudio/best"
    return (
        f"bestvideo[height<={height}]+bestaudio/"
        f"best[height<={height}]/best"
    )


def _build_out_template(work_dir: Path, filename: str | None) -> str:
    if filename:
        return str(work_dir / f"{filename}.%(ext)s")
    return str(work_dir / "%(title).200s.%(ext)s")


def _download_media(
    url: str,
    work_dir: Path,
    extension: str,
    quality: str | None,
    filename: str | None,
) -> Path:
    out_template = _build_out_template(work_dir, filename)

    if _is_audio_extension(extension):
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": extension,
                    "preferredquality": "192",
                }
            ],
            "quiet": True,
            "no_warnings": True,
        }
    else:
        ydl_opts = {
            "format": _video_format_selector(quality),
            "outtmpl": out_template,
            "merge_output_format": extension,
            "quiet": True,
            "no_warnings": True,
        }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if "requested_downloads" in info and info["requested_downloads"]:
            return Path(info["requested_downloads"][0]["filepath"])
        prepared = ydl.prepare_filename(info)
        path = Path(prepared)
        if path.exists():
            return path
        for candidate in work_dir.iterdir():
            if candidate.is_file():
                return candidate
    raise FileNotFoundError("Downloaded file not found")


def _upload_and_presign(
    local_path: Path,
    filename: str | None = None,
) -> tuple[str, str, str]:
    if not BUCKET_NAME:
        raise RuntimeError("BUCKET_NAME is required for AWS Lambda mode")
    ext = local_path.suffix.lower() or f".{DEFAULT_AUDIO_EXTENSION}"
    if filename:
        key = f"downloads/{filename}{ext}"
        display_name = f"{filename}{ext}"
    else:
        key = f"downloads/{uuid.uuid4()}{ext}"
        display_name = local_path.name

    content_type = CONTENT_TYPES.get(ext, "application/octet-stream")
    s3_client.upload_file(
        str(local_path),
        BUCKET_NAME,
        key,
        ExtraArgs={"ContentType": content_type},
    )
    presigned_url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET_NAME, "Key": key},
        ExpiresIn=PRESIGNED_EXPIRY,
    )
    return key, presigned_url, display_name


def _cleanup(work_dir: Path) -> None:
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)


def lambda_handler(event, context):
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return _response(204, {})

    try:
        body = _parse_body(event)
    except (json.JSONDecodeError, TypeError):
        return _response(400, {"error": "Invalid JSON body"})

    url = (body.get("url") or "").strip()
    if not url:
        return _response(400, {"error": "Missing required field: url"})

    try:
        extension = _normalize_extension(body.get("extension"))
    except ValueError as exc:
        return _response(400, {"error": str(exc)})

    filename = _sanitize_filename(body.get("filename") or "")
    if body.get("filename") and not filename:
        return _response(
            400,
            {"error": "filename must contain only letters, numbers, dash, or underscore"},
        )

    quality = (body.get("quality") or "720").strip().lower()
    if not _is_audio_extension(extension) and quality not in QUALITY_HEIGHT_MAP:
        return _response(
            400,
            {"error": f"Invalid quality: {quality}. Allowed: {', '.join(QUALITY_HEIGHT_MAP)}"},
        )

    work_dir = TMP_DIR / f"dl-{uuid.uuid4()}"
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        local_file = _download_media(
            url,
            work_dir,
            extension,
            quality if not _is_audio_extension(extension) else None,
            filename or None,
        )
        key, presigned_url, display_name = _upload_and_presign(
            local_file,
            filename or None,
        )
        return _response(
            200,
            {
                "presigned_url": presigned_url,
                "key": key,
                "expires_in": PRESIGNED_EXPIRY,
                "filename": display_name,
            },
        )
    except yt_dlp.utils.DownloadError as exc:
        logger.exception("yt-dlp download failed")
        return _response(422, {"error": f"Download failed: {exc}"})
    except Exception as exc:
        logger.exception("Unhandled error")
        return _response(500, {"error": str(exc)})
    finally:
        _cleanup(work_dir)
