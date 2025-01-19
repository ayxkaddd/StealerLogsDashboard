from typing import List

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from helpers import (
    extract_logs_info,
    load_cache,
    run_rg_query
)
from models import (
    FileInfo,
    FileListResponse,
    LogCredential
)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/api/logs/search/", response_model=List[LogCredential])
async def search_logs(query: str):
    run_rg_query(query.strip())

    extracted_logs = []
    try:
        with open("/tmp/logs.txt", "r", encoding='utf-8', errors='ignore') as f:
            logs = f.readlines()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    lines_seen = set()
    for log in logs:
        extracted_log = extract_logs_info(log)
        line = extracted_log.domain + extracted_log.uri + extracted_log.email + extracted_log.password
        if LogCredential.model_validate(extracted_log).domain != '':
            if line not in lines_seen:
                extracted_logs.append(extracted_log)
                lines_seen.add(line)

    return extracted_logs


@app.get("/api/logs/files/", response_model=FileListResponse)
async def get_files():
    cache = load_cache()

    files_data = []
    for file in cache:
        stats = FileInfo(
            filename=file['name'],
            creation_time=file['timestamp'],
            line_count=file['lines_count']
        )
        files_data.append(stats)

    return FileListResponse(files=files_data)


@app.get('/')
def logs_page(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")
