import logging
import tempfile
from pathlib import Path
from typing import IO
from zipfile import ZipFile

from aiohttp import ClientSession, ClientTimeout, TCPConnector, ClientResponse
from attrs import define


logger = logging.getLogger(__name__)


class SizeExceededException(Exception):
    def __init__(self, message: str):
        self.message = message


class UnexpectedResponseException(Exception):
    def __init__(self, message: str, status_code: int):
        self.message = message
        self.status_code = status_code


@define
class PipelineDownloadConfig:
    local_path: str
    max_size: int = 32 * 1024 * 1024
    chunk_size: int = 8192
    timeout: int = 30
    max_connections: int = 10
    max_connections_per_host: int = 5


@define
class PipelineFileResponse:
    file_paths: list[Path]
    etag: str
    last_modified: str


def _get_request_headers(etag: str | None, last_modified: str | None):
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


def _extract_files(path_prefix: Path, buffer: IO[bytes]) -> list[Path]:
    with ZipFile(buffer) as zf:
        valid_names = [
            name
            for name in zf.namelist()
            if not (name.startswith("/") or ".." in name) and name.endswith(".yaml")
        ]
        zf.extractall(path_prefix, valid_names)
    return [path_prefix / name for name in valid_names]


class PipelineDownloader:
    """
    Downloads files from multiple locations, checking them for updates.

    Through configuration, enforces certain size limits.
    """

    def __init__(self, client_config: PipelineDownloadConfig):
        self._config = client_config
        self._local_path = Path(client_config.local_path)
        self._session = None

    def _get_session(self) -> ClientSession:
        timeout = ClientTimeout(total=self._config.timeout)
        connector = TCPConnector(
            limit=self._config.max_connections,
            limit_per_host=self._config.max_connections_per_host,
        )
        return ClientSession(timeout=timeout, connector=connector)

    def __enter__(self):
        self._session = self._get_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            self._session.close()
            self._session = None

    def _verify_content_length(self, headers: dict[str, str]) -> int | None:
        content_length_str = headers.get("Content-Length")
        if not content_length_str or not isinstance(content_length_str, str):
            # Header not passed or invalid, continue
            return None
        if content_length_str.isnumeric():
            if (content_length := int(content_length_str)) > self._config.max_size:
                raise SizeExceededException(
                    f"Reported file size {content_length} exceeds limit ({self._config.max_size})."
                )
            return content_length
        # Do not fail yet, if header was invalid
        return None

    async def _process_response(
        self, response: ClientResponse, path_prefix: Path
    ) -> PipelineFileResponse:
        self._verify_content_length(response.headers)
        read_total = 0
        is_zip = response.content_type.endswith("zip")
        if is_zip:
            file_path = None
            file = tempfile.TemporaryFile("wb")
        else:
            if response.content_disposition and response.content_disposition.filename:
                file_path = path_prefix / (response.content_disposition.filename)
            else:
                file_path = path_prefix / "pipeline.yaml"
            file = file_path.open("wb")
        with file:
            async for chunk in response.content.iter_chunked(self._config.chunk_size):
                read_total += len(chunk)
                if read_total > self._config.max_size:
                    raise SizeExceededException(
                        f"Processed file size {read_total} exceeds limit ({self._config.max_size})."
                    )
                file.write(chunk)
            if is_zip:
                names = _extract_files(path_prefix, file)
            else:
                names = [file_path]

        return PipelineFileResponse(
            names,
            response.headers.get("ETag"),
            response.headers.get("Last-Modified"),
        )

    async def get_pipeline_files(
        self,
        name: str,
        url: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> tuple[bool, PipelineFileResponse | None]:
        """
        Fetches a single file from the given URL.

        etag and last_modified can be provided optionally from a previous
        response.
        """
        if not self._session:
            raise RuntimeError("Session not initialized.")
        headers = _get_request_headers(etag, last_modified)
        async with self._session.get(url, headers=headers) as response:
            response.raise_for_status()
            if response.status == 304:
                logger.debug(f"File at {url} unchanged.")
                return False, None
            elif response.status == 200:
                logger.info(f"Reading file from {url}.")
                path = self._local_path / name
                path.mkdir(parents=True, exist_ok=True)
                return True, await self._process_response(response, path)
            else:
                raise UnexpectedResponseException(
                    "Unexpected status code returned in response", response.status
                )
