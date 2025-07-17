import asyncio
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
import re
from typing import List, Generator, Optional, Dict, Any
from contextlib import asynccontextmanager
import logging
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import or_, select, insert, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from models.log_models import Log, LogCredential, SearchField, SearchRequest
from config import DATABASE_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ANDROID_DOMAIN_PATTERN = re.compile(
    r"(?:.*==@|android://(?:[^@/]+@)?)([^/:]+)", re.IGNORECASE
)
SPLIT_PATTERN = re.compile(r"[\s:|]+")
URL_PROTOCOL_PREFIX = re.compile(r"^https?://", re.IGNORECASE)
DOMAIN_LIKE_PATTERN = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(?::\d+)?(?:/.*)?$"
)
JSON_PATTERN = re.compile(r'^\s*\{.*\}\s*$', re.DOTALL)

MAX_FIELD_LENGTH = 200
DEFAULT_CHUNK_SIZE = 10000
DEFAULT_BATCH_SIZE = 5000
MAX_WORKERS = 8


@dataclass
class ParsedCredential:
    """Data class for parsed credential information."""
    domain: str
    uri: str
    email: str
    password: str
    created_at: datetime.datetime


class LogService:
    def __init__(self, database_url: str = DATABASE_URL):
        self.engine = create_async_engine(
            database_url,
            pool_size=20,
            max_overflow=40,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )
        self.async_session = sessionmaker(
            self.engine,
            expire_on_commit=False,
            autoflush=False,
            class_=AsyncSession
        )
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self._stats = {
            'processed_lines': 0,
            'parsed_credentials': 0,
            'failed_lines': 0
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Clean up resources."""
        await self.engine.dispose()
        self.executor.shutdown(wait=True)

    @asynccontextmanager
    async def get_session(self):
        """Context manager for database sessions."""
        async with self.async_session() as session:
            try:
                yield session
            except SQLAlchemyError as e:
                logger.error(f"Database error: {e}")
                await session.rollback()
                raise
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                await session.rollback()
                raise

    async def search_logs(self, search_request: SearchRequest) -> List[LogCredential]:
        """
        Search logs in the database based on the search request.

        Args:
            search_request: The search criteria

        Returns:
            List of matching log credentials
        """
        if not search_request.query or not search_request.query.strip():
            return []

        query = search_request.query.strip()

        if len(query) > 100:
            query = query[:100]

        async with self.get_session() as session:
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

            stmt = stmt.limit(10000)

            try:
                result = await session.execute(stmt)
                return [LogCredential(**row._asdict()) for row in result]
            except SQLAlchemyError as e:
                logger.error(f"Search query failed: {e}")
                return []

    def _chunk_file(
        self, file_path: str, chunk_size: int = DEFAULT_CHUNK_SIZE
    ) -> Generator[List[str], None, None]:
        """
        Read file in chunks to manage memory usage.

        Args:
            file_path: Path to the file to read
            chunk_size: Number of lines per chunk

        Yields:
            Lists of lines from the file
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = []
                for line_num, line in enumerate(f, 1):
                    lines.append(line)
                    if len(lines) >= chunk_size:
                        yield lines
                        lines = []

                    if line_num % 100000 == 0:
                        logger.info(f"Processed {line_num} lines from {file_path}")

                if lines:
                    yield lines
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            raise
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise

    async def insert_logs_from_file(
        self,
        file_path: str,
        batch_size: int = DEFAULT_BATCH_SIZE,
        use_upsert: bool = False
    ) -> Dict[str, int]:
        """
        Insert logs from a file into the database.

        Args:
            file_path: Path to the log file
            batch_size: Number of records to insert per batch
            use_upsert: Whether to use upsert (PostgreSQL only)

        Returns:
            Dictionary with processing statistics
        """
        now = datetime.datetime.now()
        self._stats = {'processed_lines': 0, 'parsed_credentials': 0, 'failed_lines': 0}

        logger.info(f"Starting to process file: {file_path}")

        async with self.get_session() as session:
            chunk_count = 0

            for chunk in self._chunk_file(file_path):
                chunk_count += 1
                self._stats['processed_lines'] += len(chunk)

                try:
                    batch_values = await self._parse_chunk_async(chunk, now)

                    if not batch_values:
                        continue

                    self._stats['parsed_credentials'] += len(batch_values)

                    for i in range(0, len(batch_values), batch_size):
                        batch = batch_values[i:i + batch_size]

                        if use_upsert and hasattr(self.engine.dialect, 'name') and self.engine.dialect.name == 'postgresql':
                            await self._upsert_batch_postgresql(session, batch)
                        else:
                            await session.execute(insert(Log.__table__), batch)

                    await session.commit()

                    if chunk_count % 10 == 0:
                        logger.info(f"Processed {chunk_count} chunks, {self._stats['parsed_credentials']} credentials parsed")

                except Exception as e:
                    logger.error(f"Error processing chunk {chunk_count}: {e}")
                    await session.rollback()
                    self._stats['failed_lines'] += len(chunk)
                    continue

        logger.info(f"File processing complete. Stats: {self._stats}")
        return self._stats

    async def _upsert_batch_postgresql(self, session: AsyncSession, batch: List[Dict[str, Any]]):
        """
        Perform upsert operation for PostgreSQL.

        Args:
            session: Database session
            batch: Batch of records to upsert
        """
        stmt = pg_insert(Log.__table__).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=['domain', 'email'],
            set_=dict(password=stmt.excluded.password, created_at=stmt.excluded.created_at)
        )
        await session.execute(stmt)

    async def _parse_chunk_async(self, chunk: List[str], now: datetime.datetime) -> List[Dict[str, Any]]:
        """
        Parse a chunk of lines asynchronously.

        Args:
            chunk: List of lines to parse
            now: Timestamp for creation time

        Returns:
            List of parsed credential dictionaries
        """
        return await asyncio.get_event_loop().run_in_executor(
            self.executor, self._parse_chunk, chunk, now
        )

    def _parse_chunk(self, chunk: List[str], now: datetime.datetime) -> List[Dict[str, Any]]:
        """
        Parse a chunk of lines synchronously.

        Args:
            chunk: List of lines to parse
            now: Timestamp for creation time

        Returns:
            List of parsed credential dictionaries
        """
        results = []
        for line in chunk:
            try:
                if parsed := self._parse_log_line(line, now):
                    results.append(parsed)
            except Exception as e:
                logger.warning(f"Failed to parse line: {line[:100]}... Error: {e}")
                continue
        return results

    def _is_valid_url(self, candidate: str) -> bool:
        """
        Check if the candidate is a valid URL (with or without protocol).

        Args:
            candidate: String to validate

        Returns:
            True if valid URL, False otherwise
        """
        if not candidate or len(candidate) > 2048:
            return False

        return bool(
            URL_PROTOCOL_PREFIX.match(candidate)
            or DOMAIN_LIKE_PATTERN.match(candidate)
            or candidate.startswith("localhost")
        )

    def _sanitize_field(self, field: str, max_length: int = MAX_FIELD_LENGTH) -> str:
        """
        Sanitize and truncate field values.

        Args:
            field: Field value to sanitize
            max_length: Maximum allowed length

        Returns:
            Sanitized field value
        """
        if not field:
            return ""

        sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', str(field))
        return sanitized[:max_length].strip()

    def _parse_log_line(self, line: str, now: datetime.datetime) -> Optional[Dict[str, Any]]:
        """
        Parse a log line and extract domain, URI, email, and password information.

        Args:
            line: Log line to parse
            now: Creation timestamp

        Returns:
            Dictionary with parsed credential data or None if parsing fails
        """
        line = line.replace("\x00", " ").strip()
        if not line or len(line) > 10000:
            return None

        if JSON_PATTERN.match(line):
            return None

        if domain_match := ANDROID_DOMAIN_PATTERN.search(line):
            domain_part = domain_match.group(1).strip("/:")
            remaining = line.split(domain_part, 1)[-1].lstrip(":/| ")
            parts = SPLIT_PATTERN.split(remaining)

            return {
                "domain": self._sanitize_field(f"android://{domain_part}"),
                "uri": "/",
                "email": self._sanitize_field(parts[0] if parts else ""),
                "password": self._sanitize_field(parts[1] if len(parts) > 1 else ""),
                "created_at": now,
            }

        parts = [p.strip() for p in line.split(":", 2)]

        if parts and self._is_valid_url(parts[0]):
            url_part = parts[0]
            email = parts[1] if len(parts) > 1 else ""
            password = parts[2] if len(parts) > 2 else ""
        elif len(parts) > 2 and self._is_valid_url(parts[2]):
            url_part = parts[2]
            email = parts[0]
            password = parts[1]
        else:
            clean_line = line.replace("http://", "").replace("https://", "")
            parts_fallback = [p for p in SPLIT_PATTERN.split(clean_line) if p]

            if not parts_fallback:
                return None

            password = parts_fallback[-1]
            email = (
                parts_fallback[-2].split(":", 1)[0]
                if len(parts_fallback) > 1
                else ""
            )
            url_part = (
                ":".join(parts_fallback[:-2])
                if len(parts_fallback) > 2
                else clean_line
            )

        url_clean = url_part.replace("http://", "").replace("https://", "")
        domain_parts = url_clean.split("/", 1)
        domain = domain_parts[0].strip("/:") if domain_parts else ""
        uri = f"/{domain_parts[1]}" if len(domain_parts) > 1 else "/"

        if not domain or not self._is_valid_url(domain):
            return None

        return {
            "domain": self._sanitize_field(domain),
            "uri": self._sanitize_field(uri),
            "email": self._sanitize_field(email),
            "password": self._sanitize_field(password),
            "created_at": now,
        }

    async def get_stats(self) -> Dict[str, Any]:
        async with self.get_session() as session:
            try:
                result = await session.execute(text("""
                    SELECT reltuples::bigint as estimate
                    FROM pg_class
                    WHERE relname = :table_name
                """), {"table_name": "logs"})

                estimated_count = result.scalar()

                return {
                    **self._stats,
                    'total_records_in_db': estimated_count
                }
            except SQLAlchemyError as e:
                logger.error(f"Error getting stats: {e}")
                return self._stats
