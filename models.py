from typing import List
from pydantic import BaseModel

class LogCredential(BaseModel):
    domain: str
    uri: str
    email: str
    password: str

class FileInfo(BaseModel):
    filename: str
    creation_time: str
    line_count: int

class FileListResponse(BaseModel):
    files: List[FileInfo]