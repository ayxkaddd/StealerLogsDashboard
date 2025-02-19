import asyncio
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
import re
from typing import List, Generator, Optional
from sqlalchemy import or_, select, insert
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from models.log_models import Log, LogCredential, SearchField, SearchRequest
from config import DATABASE_URL

ANDROID_DOMAIN_PATTERN = re.compile(
    r"(?:.*==@|android://(?:[^@/]+@)?)([^/:]+)", re.IGNORECASE
)
SPLIT_PATTERN = re.compile(r"[\s:|]+")
URL_PROTOCOL_PREFIX = re.compile(r"^https?://", re.IGNORECASE)
DOMAIN_LIKE_PATTERN = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(?::\d+)?(?:/.*)?$"
)


class LogService:
    def __init__(self):
        self.engine = create_async_engine(
            DATABASE_URL,
            pool_size=20,  # Increased for better concurrent performance
            max_overflow=40,
            pool_pre_ping=True,  # Connection health check
        )
        self.async_session = sessionmaker(
            self.engine, expire_on_commit=False, autoflush=False, class_=AsyncSession
        )
        self.executor = ThreadPoolExecutor(max_workers=8)

    async def search_logs(self, search_request: SearchRequest) -> List[LogCredential]:
        """
        Search logs in the database based on the search request.
        """
        async with self.async_session() as session:
            query = search_request.query.strip()

            stmt = select(Log.domain, Log.uri, Log.email, Log.password)

            if search_request.field == SearchField.ALL:
                stmt = stmt.where(
                    or_(
                        Log.domain.ilike(f"%{query}%"),
                        Log.email.ilike(f"%{query}%"),
                        Log.password.ilike(f"%{query}%"),
                    )
                )
            elif search_request.field == SearchField.DOMAIN:
                stmt = stmt.where(Log.domain.ilike(f"%{query}%"))
            elif search_request.field == SearchField.EMAIL:
                stmt = stmt.where(Log.email.ilike(f"%{query}%"))
            elif search_request.field == SearchField.PASSWORD:
                stmt = stmt.where(Log.password.ilike(f"%{query}%"))

            result = await session.execute(stmt)
            return [LogCredential(**row._asdict()) for row in result]

    def _chunk_file(
        self, file_path: str, chunk_size: int = 10000
    ) -> Generator[List[str], None, None]:
        lines = []
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                lines.append(line)
                if len(lines) >= chunk_size:
                    yield lines
                    lines = []
            if lines:
                yield lines

    async def insert_logs_from_file(self, file_path: str, batch_size: int = 5000):
        now = datetime.datetime.now()

        async with self.async_session() as session:
            for chunk in self._chunk_file(file_path):
                batch_values = await self._parse_chunk_async(chunk, now)

                for i in range(0, len(batch_values), batch_size):
                    await session.execute(
                        insert(Log.__table__), batch_values[i : i + batch_size]
                    )
                await session.commit()

    async def _parse_chunk_async(self, chunk: List[str], now: datetime.datetime):
        return await asyncio.get_event_loop().run_in_executor(
            self.executor, self._parse_chunk, chunk, now
        )

    def _parse_chunk(self, chunk: List[str], now: datetime.datetime) -> List[dict]:
        return [
            cred
            for line in chunk
            if (cred := self._parse_log_line(line, now)) is not None
        ]

    def _is_valid_url(self, candidate: str) -> bool:
        """Check if the candidate is a valid URL (with or without protocol)."""
        return bool(
            URL_PROTOCOL_PREFIX.match(candidate)
            or DOMAIN_LIKE_PATTERN.match(candidate)
            or candidate.startswith("localhost")
        )

    def _parse_log_line(self, line: str, now: datetime.datetime) -> Optional[dict]:
        """Parse a log line and extract domain, URI, email, and password information."""
        line = line.replace("\x00", " ").strip()
        if not line:
            return None

        if line[0] == "{" and line[-1] == "}" and '"' in line:
            return None

        if domain_match := ANDROID_DOMAIN_PATTERN.search(line):
            domain_part = domain_match.group(1).strip("/:")
            remaining = line.split(domain_part, 1)[-1].lstrip(":/| ")
            parts = SPLIT_PATTERN.split(remaining)
            return {
                "domain": f"android://{domain_part}"[:200],
                "uri": "/",
                "email": parts[0][:200] if parts else "",
                "password": parts[1][:200] if len(parts) > 1 else "",
                "created_at": now,
            }

        parts = [p.strip() for p in line.split(":", 2)]

        if parts and self._is_valid_url(parts[0]):
            url_part = parts[0]
            email = parts[1][:200] if len(parts) > 1 else ""
            password = parts[2][:200] if len(parts) > 2 else ""
        elif len(parts) > 2 and self._is_valid_url(parts[2]):
            url_part = parts[2]
            email = parts[0][:200]
            password = parts[1][:200]
        else:
            clean_line = line.replace("http://", "").replace("https://", "")
            parts_fallback = [p for p in SPLIT_PATTERN.split(clean_line) if p]
            if not parts_fallback:
                return None

            password = parts_fallback[-1][:200]
            email = (
                parts_fallback[-2].split(":", 1)[0][:200]
                if len(parts_fallback) > 1
                else ""
            )
            url_part = (
                ":".join(parts_fallback[:-2]) if len(parts_fallback) > 2 else clean_line
            )

        url_clean = url_part.replace("http://", "").replace("https://", "")
        domain, *uri_parts = url_clean.split("/", 1)

        return {
            "domain": domain.strip("/:")[:200],
            "uri": f"/{uri_parts[0]}"[:200] if uri_parts else "/",
            "email": email,
            "password": password,
            "created_at": now,
        }
