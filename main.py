import datetime
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, status, Depends, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict
import uvicorn

from config import API_ID, API_HASH, ALLOWED_HOSTS, LOG_LEVEL
from services.log_service import LogService
from services.file_service import FileService
from services.telegram_service import TelegramLogFetcher
from models.log_models import (
    LogCredential,
    FileListResponse,
    SearchRequest,
    TelegramSearchResponse,
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ImportLogsRequest(BaseModel):
    file_path: str = Field(..., description="Path to the log file to import")
    batch_size: int = Field(default=5000, ge=100, le=10000, description="Batch size for import")
    use_upsert: bool = Field(default=False, description="Use upsert instead of insert")

class ImportLogsResponse(BaseModel):
    message: str
    task_id: str
    stats: Optional[Dict[str, Any]] = None

class StatsResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    stats: Dict[str, Any]
    timestamp: datetime.datetime

class ErrorResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    error: str
    detail: str
    timestamp: datetime.datetime

background_tasks_status = {}

async def get_log_service():
    """Dependency to get log service instance."""
    return LogService()

async def get_file_service():
    """Dependency to get file service instance."""
    return FileService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting Logs API application...")

    try:
        log_service = LogService()
        await log_service.get_stats()
        logger.info("Database connection established successfully")

        app.state.log_service = log_service
        app.state.file_service = FileService()

        yield
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise
    finally:
        logger.info("Shutting down Logs API application...")
        if hasattr(app.state, 'log_service'):
            await app.state.log_service.close()

class LogsAPI:
    def __init__(self):
        self.app = FastAPI(
            title="Logs API",
            version="1.0.0",
            description="API for managing and searching log credentials",
            lifespan=lifespan,
            docs_url="/docs" if os.getenv("ENVIRONMENT") != "production" else None,
            redoc_url="/redoc" if os.getenv("ENVIRONMENT") != "production" else None,
        )

        self.setup_middleware()
        self.setup_static_files()
        self.setup_routes()
        self.setup_exception_handlers()

        self.templates = Jinja2Templates(directory="templates")

    def setup_middleware(self):
        """Setup application middleware."""

        if hasattr(self, 'ALLOWED_HOSTS') and ALLOWED_HOSTS:
            self.app.add_middleware(
                TrustedHostMiddleware,
                allowed_hosts=ALLOWED_HOSTS
            )

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000", "http://localhost:8000"],
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    def setup_static_files(self):
        """Setup static file serving."""
        static_dir = Path("static")
        if static_dir.exists():
            self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    def setup_exception_handlers(self):
        """Setup global exception handlers."""

        @self.app.exception_handler(HTTPException)
        async def http_exception_handler(request: Request, exc: HTTPException):
            return JSONResponse(
                status_code=exc.status_code,
                content=ErrorResponse(
                    error=exc.detail,
                    detail=f"HTTP {exc.status_code}",
                    timestamp=datetime.datetime.now()
                ).model_dump(mode='json')
            )

        @self.app.exception_handler(Exception)
        async def general_exception_handler(request: Request, exc: Exception):
            logger.error(f"Unhandled exception: {exc}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content=ErrorResponse(
                    error="Internal server error",
                    detail=str(exc) if os.getenv("ENVIRONMENT") != "production" else "An error occurred",
                    timestamp=datetime.datetime.now()
                ).model_dump(mode='json')
            )

    def setup_routes(self):
        """Setup API routes."""

        self.app.get("/", include_in_schema=False)(self.logs_page)
        self.app.get("/health")(self.health_check)

        self.app.post("/api/logs/search/", response_model=List[LogCredential])(self.search_logs)
        self.app.get("/api/logs/files/", response_model=FileListResponse)(self.get_files)
        self.app.post("/api/logs/import/", response_model=ImportLogsResponse)(self.import_logs)
        self.app.get("/api/logs/stats/", response_model=StatsResponse)(self.get_stats)
        self.app.post("/api/logs/search-telegram/", response_model=TelegramSearchResponse)(self.search_telegram_logs)
        self.app.get("/api/logs/import-status/{task_id}")(self.get_import_status)

    async def health_check(self) -> Dict[str, Any]:
        """Health check endpoint."""
        try:
            async with LogService() as log_service:
                await log_service.get_stats()

            return {
                "status": "healthy",
                "timestamp": datetime.datetime.now(),
                "version": "1.0.0"
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service unhealthy"
            )

    async def get_stats(
        self,
        log_service: LogService = Depends(get_log_service)
    ) -> StatsResponse:
        """Get statistics about the logs."""
        try:
            async with log_service:
                stats = await log_service.get_stats()
                return StatsResponse(
                    stats=stats,
                    timestamp=datetime.datetime.now()
                )
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve statistics"
            )

    async def search_logs(
        self,
        search_request: SearchRequest,
        log_service: LogService = Depends(get_log_service)
    ) -> List[LogCredential]:
        """Search logs based on query string."""

        if not search_request.query or len(search_request.query.strip()) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query must be at least 2 characters long"
            )

        try:
            async with log_service:
                results = await log_service.search_logs(search_request)
                logger.info(f"Search query '{search_request.query}' returned {len(results)} results")
                return results
        except Exception as e:
            logger.error(f"Error searching logs: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to search logs"
            )

    async def get_files(
        self,
        file_service: FileService = Depends(get_file_service)
    ) -> FileListResponse:
        """Get list of files with their statistics."""
        try:
            return await file_service.get_files_info()
        except Exception as e:
            logger.error(f"Error getting files: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve file information"
            )

    async def import_logs(
        self,
        import_request: ImportLogsRequest,
        background_tasks: BackgroundTasks,
    ) -> ImportLogsResponse:
        """Import logs from a file into the database."""

        file_path = Path(import_request.file_path)
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found: {import_request.file_path}"
            )

        if not file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path must be a file"
            )

        task_id = f"import_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        background_tasks_status[task_id] = {"status": "started", "progress": 0}

        background_tasks.add_task(
            self._import_logs_background,
            task_id,
            str(file_path),
            import_request.batch_size,
            import_request.use_upsert
        )

        return ImportLogsResponse(
            message="Import started successfully",
            task_id=task_id
        )

    async def _import_logs_background(
        self,
        task_id: str,
        file_path: str,
        batch_size: int,
        use_upsert: bool
    ):
        """Background task for importing logs."""
        try:
            background_tasks_status[task_id]["status"] = "processing"

            async with LogService() as log_service:
                stats = await log_service.insert_logs_from_file(
                    file_path,
                    batch_size=batch_size,
                    use_upsert=use_upsert
                )

                background_tasks_status[task_id] = {
                    "status": "completed",
                    "progress": 100,
                    "stats": stats
                }

        except Exception as e:
            logger.error(f"Import task {task_id} failed: {e}")
            background_tasks_status[task_id] = {
                "status": "failed",
                "error": str(e)
            }

    async def get_import_status(
        self,
        task_id: str
    ) -> Dict[str, Any]:
        """Get status of an import task."""
        if task_id not in background_tasks_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )

        response_data = {
            "task_id": task_id,
            **background_tasks_status[task_id],
            "timestamp": datetime.datetime.now().isoformat()
        }

        return response_data

    async def search_telegram_logs(
        self,
        search_request: SearchRequest
    ) -> Dict[str, Any]:
        """Search logs via Telegram bot."""

        if not search_request.query or len(search_request.query.strip()) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query must be at least 2 characters long"
            )

        try:
            telegram_fetcher = TelegramLogFetcher(
                api_id=int(API_ID),
                api_hash=API_HASH
            )

            file_path, result_count = await telegram_fetcher.fetch_logs(
                search_request.query
            )

            if result_count == 0:
                return {"results": [], "file_path": "", "count": 0}

            if not file_path:
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="No response from Telegram bot"
                )

            credentials = []
            file_path_obj = Path(file_path)

            if file_path_obj.exists():
                async with LogService() as log_service:
                    with open(file_path_obj, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    parsed = log_service._parse_log_line(
                                        line,
                                        now=datetime.datetime.now()
                                    )
                                    if parsed:
                                        credentials.append(LogCredential(**parsed).dict())
                                except Exception as e:
                                    logger.warning(f"Failed to parse telegram result line: {e}")
                                    continue

            return {
                "results": credentials,
                "file_path": str(file_path),
                "count": len(credentials),
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Telegram search failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to search Telegram logs"
            )

    async def logs_page(self, request: Request):
        """Render the main logs viewer page."""
        try:
            return self.templates.TemplateResponse(
                request=request,
                name="index.html",
                context={"title": "Logs Viewer"}
            )
        except Exception as e:
            logger.error(f"Error rendering logs page: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to render page"
            )


def create_app() -> FastAPI:
    """Factory function to create the FastAPI app."""
    return LogsAPI().app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )