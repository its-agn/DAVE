from __future__ import annotations

import json
from pathlib import Path
from typing import Any, BinaryIO, Mapping, TextIO


class JSONParseError(ValueError):
    """Raised when JSON input cannot be decoded."""


class JSONParser:
    """
    Generic JSON parser for HTTP bodies, files, and file-like streams.

    HTTP transfer details, including chunked transfer encoding, are handled
    by the web server before the body reaches this class.
    """

    def parse_http_body(
        self,
        body: bytes | bytearray | str | Mapping[str, Any],
    ) -> dict[str, Any]:
        """
        Parse a complete HTTP JSON request body.

        Web frameworks may provide the body as raw bytes, decoded text,
        or an already-decoded mapping.
        """
        if isinstance(body, Mapping):
            payload: Any = dict(body)
        elif isinstance(body, (bytes, bytearray)):
            payload = self._parse_bytes(bytes(body))
        elif isinstance(body, str):
            payload = self._parse_text(body)
        else:
            raise JSONParseError(
                "HTTP body must be bytes, text, or a mapping."
            )

        return self._require_object(payload)

    def parse_file(
        self,
        path: str | Path,
    ) -> dict[str, Any]:
        """Parse a JSON object from a UTF-8 file."""
        file_path = Path(path)

        if not file_path.is_file():
            raise JSONParseError(
                f"JSON file does not exist: {file_path}"
            )

        try:
            with file_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except UnicodeDecodeError as exc:
            raise JSONParseError(
                f"JSON file must use UTF-8 encoding: {file_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise self._decode_error(exc, source=str(file_path)) from exc
        except OSError as exc:
            raise JSONParseError(
                f"Unable to read JSON file: {file_path}"
            ) from exc

        return self._require_object(payload)

    def parse_stream(
        self,
        stream: BinaryIO | TextIO,
    ) -> dict[str, Any]:
        """
        Parse a JSON object from an open binary or text stream.

        This supports uploaded files and test streams. It does not implement
        asynchronous HTTP streaming; that remains the API layer's job.
        """
        try:
            content = stream.read()
        except OSError as exc:
            raise JSONParseError("Unable to read JSON stream.") from exc

        if isinstance(content, bytes):
            payload = self._parse_bytes(content)
        elif isinstance(content, str):
            payload = self._parse_text(content)
        else:
            raise JSONParseError(
                "JSON stream must return bytes or text."
            )

        return self._require_object(payload)

    def _parse_bytes(self, body: bytes) -> Any:
        if not body:
            raise JSONParseError("JSON input cannot be empty.")

        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise JSONParseError(
                "JSON input must use UTF-8 encoding."
            ) from exc

        return self._parse_text(text)

    def _parse_text(self, text: str) -> Any:
        if not text.strip():
            raise JSONParseError("JSON input cannot be empty.")

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise self._decode_error(exc) from exc

    @staticmethod
    def _require_object(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise JSONParseError(
                "The top-level JSON value must be an object."
            )

        return payload

    @staticmethod
    def _decode_error(
        error: json.JSONDecodeError,
        source: str = "JSON input",
    ) -> JSONParseError:
        return JSONParseError(
            f"Invalid JSON in {source} at line {error.lineno}, "
            f"column {error.colno}: {error.msg}"
        )