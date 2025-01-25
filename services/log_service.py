import asyncio
import datetime
import json
import re
from typing import List, Generator, Optional
from sqlalchemy import select, bindparam, insert
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from models.log_models import Log, LogCredential
from config import DATABASE_URL

class LogService:
    def __init__(self):
        self.engine = create_async_engine(
            DATABASE_URL,
            pool_size=20,  # Increased for better concurrent performance
            max_overflow=40,
            pool_pre_ping=True  # Connection health check
        )
        self.async_session = sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    async def search_logs(self, query: str, bulk: bool = False) -> List[LogCredential]:
        """
        Search logs in the database based on the query string.
        """
        async with self.async_session() as session:
            stmt = select(Log).where(
                Log.domain.ilike(f"%{query}") |
                Log.email.ilike(f"%{query}%") |
                Log.password.ilike(f"%{query}%")
            )
            result = await session.execute(stmt)
            logs = result.scalars().all()

            return [
                LogCredential(
                    domain=log.domain,
                    uri=log.uri,
                    email=log.email,
                    password=log.password,
                )
                for log in logs
            ]

    def _chunk_file(self, file_path: str, chunk_size: int = 10000) -> Generator[List[str], None, None]:
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
            async with session.begin():
                for chunk in self._chunk_file(file_path):
                    batch_values = []
                    for line in chunk:
                        credential = await self._parse_log_line_async(line)
                        if credential and credential.domain:
                            batch_values.append({
                                "domain": credential.domain,
                                "uri": credential.uri,
                                "email": credential.email,
                                "password": credential.password,
                                "created_at": now
                            })

                        if len(batch_values) >= batch_size:
                            await session.execute(
                                insert(Log),
                                batch_values
                            )
                            batch_values = []

                    if batch_values:
                        await session.execute(
                            insert(Log),
                            batch_values
                        )

    async def _parse_log_line_async(self, line: str) -> Optional[LogCredential]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_log_line, line)

    def _parse_log_line(self, line: str) -> Optional[LogCredential]:
        line = line.replace("\x00", " ").strip()
        if not line:
            return None

        if line[0] == '{' and line[-1] == '}':
            try:
                json.loads(line)
                return None
            except json.JSONDecodeError:
                pass

        if "android://" in line:
            android_match = re.search(r'android://((?:==@)?[^:]+)', line)
            if not android_match:
                return None

            domain_part = android_match.group(1)
            if "==@" in domain_part:
                domain = f"android://{domain_part.split('@')[-1]}"
            else:
                domain = f"android://{domain_part}"

            remaining = line.split(domain, 1)[-1]
            parts = re.split(r'[ :|]+', remaining)
            return LogCredential(
                domain=domain[:200],
                uri="/"[:200],
                email=parts[0][:200] if len(parts) > 0 else "",
                password=parts[1][:200] if len(parts) > 1 else "",
            )

        clean_line = line.replace("http://", "").replace("https://", "")
        parts = re.split(r'[ :|]+', clean_line)

        email = parts[-2].strip() if len(parts) >= 2 else ""
        password = parts[-1].strip() if len(parts) >= 1 else ""
        url_part = ':'.join(parts[:-2]) if len(parts) >= 2 else clean_line

        if '/' in url_part:
            domain, uri_part = url_part.split('/', 1)
            uri = '/' + uri_part
        else:
            domain = url_part
            uri = '/'

        return LogCredential(
            domain=domain[:200],
            uri=uri[:200],
            email=email[:200],
            password=password[:200],
        )
