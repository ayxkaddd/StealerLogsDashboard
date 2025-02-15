import datetime
from typing import Any, Dict, List
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from config import API_ID, API_HASH
from services.log_service import LogService
from services.file_service import FileService
from services.telegram_service import TelegramLogFetcher
from models.log_models import (
    LogCredential,
    FileListResponse,
    SearchRequest,
    TelegramSearchResponse,
)


class LogsAPI:
    def __init__(self):
        self.app = FastAPI(title="Logs API", version="1.0.0")
        self.setup_routes()
        self.setup_static_files()
        self.log_service = LogService()
        self.file_service = FileService()
        self.templates = Jinja2Templates(directory="templates")
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def setup_static_files(self):
        self.app.mount("/static", StaticFiles(directory="static"), name="static")

    def setup_routes(self):
        self.app.post("/api/logs/search/")(self.search_logs)
        self.app.get("/api/logs/files/")(self.get_files)
        self.app.post("/api/logs/import/")(self.import_logs)
        self.app.post(
            "/api/logs/search-telegram/", response_model=TelegramSearchResponse
        )(self.search_telegram_logs)

        self.app.get("/")(self.logs_page)

    async def search_logs(self, search_request: SearchRequest) -> List[LogCredential]:
        """
        Search logs based on query string.
        """
        try:
            return await self.log_service.search_logs(search_request)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def get_files(self) -> FileListResponse:
        """
        Get list of files with their statistics.
        """
        try:
            return await self.file_service.get_files_info()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def import_logs(self, file_path: str):
        """
        Import logs from a file into the database.
        """
        try:
            await self.log_service.insert_logs_from_file(file_path)
            return {"message": "Logs imported successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def search_telegram_logs(
        self, search_request: SearchRequest
    ) -> Dict[str, Any]:
        try:
            telegram_fetcher = TelegramLogFetcher(api_id=int(API_ID), api_hash=API_HASH)
            file_path, result_count = await telegram_fetcher.fetch_logs(
                search_request.query
            )

            if result_count == 0:
                return {"results": [], "file_path": "", "count": 0}

            if not file_path:
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="No response from Telegram bot",
                )

            credentials = []
            with open(file_path, "r") as f:
                for line in f:
                    parsed = self.log_service._parse_log_line(
                        line.strip(), now=datetime.datetime.now()
                    )
                    if parsed:
                        credentials.append(LogCredential(**parsed).dict())

            return {
                "results": credentials,
                "file_path": file_path,
                "count": len(credentials),
            }

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
            )

    def logs_page(self, request: Request):
        """
        Render the main logs viewer page.
        """
        return self.templates.TemplateResponse(request=request, name="index.html")


app = LogsAPI().app
