import json
from pathlib import Path
from typing import Dict, List
from models.log_models import FileInfo, FileListResponse

class FileService:
    def __init__(self, cache_file: str = "file_stats_cache.json"):
        self.cache_file = Path(cache_file)

    async def get_files_info(self) -> FileListResponse:
        """
        Get information about all log files
        """
        cache = await self._load_cache()
        files_data = [
            FileInfo(
                filename=file['name'],
                creation_time=file['timestamp'],
                line_count=file['lines_count']
            )
            for file in cache
        ]
        return FileListResponse(files=files_data)

    async def _load_cache(self) -> List[Dict]:
        """
        Load file statistics from cache
        """
        try:
            cache_content = self.cache_file.read_text()
            return json.loads(cache_content)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

