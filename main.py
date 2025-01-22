from typing import List
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from services.log_service import LogService
from services.file_service import FileService
from models.log_models import LogCredential, FileListResponse

class LogsAPI:
    def __init__(self):
        self.app = FastAPI(title="Logs API", version="1.0.0")
        self.setup_routes()
        self.setup_static_files()
        self.log_service = LogService()
        self.file_service = FileService()
        self.templates = Jinja2Templates(directory="templates")

    def setup_static_files(self):
        self.app.mount("/static", StaticFiles(directory="static"), name="static")

    def setup_routes(self):
        self.app.get("/api/logs/search")(self.search_logs)
        self.app.get("/api/logs/files/")(self.get_files)
        self.app.post("/api/logs/import")(self.import_logs)
        self.app.get("/")(self.logs_page)

    async def search_logs(self, query: str, bulk: bool = False) -> List[LogCredential]:
        """
        Search logs based on query string.
        """
        try:
            return await self.log_service.search_logs(query.strip(), bulk)
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

    def logs_page(self, request: Request):
        """
        Render the main logs viewer page.
        """
        return self.templates.TemplateResponse(
            request=request,
            name="index.html"
        )

app = LogsAPI().app
