from typing import List
import subprocess
import re
from pathlib import Path
from config import FOLDER_WITH_LOGS
from models.log_models import LogCredential

class LogService:
    def __init__(self):
        self.output_file = Path("/tmp/logs.txt")
        self.logs_directory = Path(FOLDER_WITH_LOGS)

    async def search_logs(self, query: str, bulk: bool = False) -> List[LogCredential]:
        """
        Search logs and return matching credentials
        """
        await self._execute_search(query, bulk)
        return await self._process_search_results()

    async def _execute_search(self, query: str, bulk: bool):
        """
        Execute ripgrep search command
        """
        command = self._build_search_command(query, bulk)

        try:
            with open(self.output_file, 'w') as outfile:
                subprocess.run(
                    command,
                    cwd=self.logs_directory,
                    stdout=outfile,
                    check=True
                )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Search command failed: {e}")

    def _build_search_command(self, query: str, bulk: bool) -> List[str]:
        """
        Build the ripgrep command based on search parameters
        """
        base_command = ["rg", "-i", "-g", "*.txt", "--text", "--no-line-number", "--no-filename"]

        if bulk:
            search_terms = query.split('|')
            pattern = '|'.join(re.escape(term.strip()) for term in search_terms if term.strip())
            return base_command + [pattern]

        return base_command + [re.escape(query)]

    async def _process_search_results(self) -> List[LogCredential]:
        """
        Process search results and extract credentials
        """
        try:
            with open(self.output_file, "r", encoding='utf-8', errors='ignore') as f:
                logs = f.readlines()
        except Exception as e:
            raise RuntimeError(f"Failed to read search results: {e}")

        return self._extract_unique_credentials(logs)

    def _extract_unique_credentials(self, logs: List[str]) -> List[LogCredential]:
        """
        Extract unique credentials from log lines
        """
        credentials = []
        seen_lines = set()

        for log in logs:
            credential = self._parse_log_line(log)
            if not credential.domain:
                continue

            line_hash = hash(f"{credential.domain}{credential.uri}{credential.email}{credential.password}")
            if line_hash not in seen_lines:
                credentials.append(credential)
                seen_lines.add(line_hash)

        return credentials

    def _parse_log_line(self, line: str) -> LogCredential:
        """
        Parse a log line into a LogCredential object
        """
        line = line.replace(" ", ":").replace("|", ":")

        # Extract URL parts
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
            password=parts[2].strip() if len(parts) > 2 else ""
        )

