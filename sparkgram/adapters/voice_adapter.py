"""
Audio and Voice-to-Code Adapter for SparkGram.
Transcribes voice notes via Groq Whisper API with developer prompt biasing.
"""
import os
import io
import logging
from typing import Optional, Tuple
import urllib.request
import urllib.error
import json

log = logging.getLogger(__name__)

# Developer technical bias prompt to prevent Whisper code-slang hallucinations
DEV_PROMPT_BIAS = (
    "Python, JavaScript, TypeScript, async, await, Pydantic, refactor, class, "
    "function, try, except, git, commit, bug, pull request, Docker, API, endpoint, "
    "subprocess, database, query, test, pytest, fix, format, lint"
)


class VoiceAdapter:
    """Handles audio transcription via Groq Whisper API or fallback."""

    @staticmethod
    async def transcribe_audio_bytes(
        audio_bytes: bytes,
        filename: str = "voice.oga",
        groq_api_key: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Transcribes audio payload to text using Groq Whisper API."""
        api_key = groq_api_key or os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            return False, "GROQ_API_KEY tidak dikonfigurasi di .env untuk transkripsi suara."

        # Multipart form data boundary
        boundary = "----SparkGramFormBoundary7MA4YWxkTrZu0gW"
        body = io.BytesIO()

        # 1. model parameter
        body.write(f"--{boundary}\r\n".encode("utf-8"))
        body.write(b'Content-Disposition: form-data; name="model"\r\n\r\n')
        body.write(b"whisper-large-v3-turbo\r\n")

        # 2. prompt bias parameter
        body.write(f"--{boundary}\r\n".encode("utf-8"))
        body.write(b'Content-Disposition: form-data; name="prompt"\r\n\r\n')
        body.write(DEV_PROMPT_BIAS.encode("utf-8") + b"\r\n")

        # 3. language parameter (auto-detect / id / en)
        body.write(f"--{boundary}\r\n".encode("utf-8"))
        body.write(b'Content-Disposition: form-data; name="response_format"\r\n\r\n')
        body.write(b"json\r\n")

        # 4. file parameter
        body.write(f"--{boundary}\r\n".encode("utf-8"))
        body.write(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"))
        body.write(b"Content-Type: audio/ogg\r\n\r\n")
        body.write(audio_bytes)
        body.write(b"\r\n")

        # End boundary
        body.write(f"--{boundary}--\r\n".encode("utf-8"))
        payload = body.getvalue()

        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_data = resp.read().decode("utf-8")
                parsed = json.loads(resp_data)
                text = parsed.get("text", "").strip()
                if text:
                    return True, text
                return False, "Transkripsi kosong dari audio."
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            log.warning(f"Whisper API error: {e.code} - {err_body}")
            return False, f"Whisper API error ({e.code}): {err_body}"
        except Exception as e:
            log.warning(f"Transcription failure: {e}")
            return False, f"Transkripsi audio gagal: {e}"
