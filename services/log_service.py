import datetime
from typing import List, Generator
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
                Log.domain.like(f"%{query}%") |
                Log.uri.like(f"%{query}%") |
                Log.email.like(f"%{query}%") |
                Log.password.like(f"%{query}%")
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
                        credential = self._parse_log_line(line)
                        if credential.domain:
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

    def _parse_log_line(self, line: str) -> LogCredential:
        line = line.replace("\x00", " ").encode("utf-8", errors="ignore").decode("utf-8")

        if "https://" in line:
            line = line.split("https://")[-1]
        elif "http://" in line:
            line = line.split("http://")[-1]

        parts = line.split(':')
        url_parts = parts[0].split("/")

        return LogCredential(
            domain=url_parts[0].strip(),
            uri="/" + "/".join(url_parts[1:]).strip() if len(url_parts) > 1 else "/",
            email=parts[1].strip() if len(parts) > 1 else "",
            password=parts[2].strip() if len(parts) > 2 else "",
        )
