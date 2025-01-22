from typing import List
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Log(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String, nullable=False)
    uri = Column(String, nullable=False)
    email = Column(String)
    password = Column(String)
    created_at = Column(TIMESTAMP, default="CURRENT_TIMESTAMP")

class LogCredential(BaseModel):
    """
    Represents log credentials extracted from log files
    """
    domain: str = Field(..., description="Domain name")
    uri: str = Field(..., description="URI path")
    email: str = Field(..., description="Email or username")
    password: str = Field(..., description="Password")

class FileInfo(BaseModel):
    """
    Information about a log file
    """
    filename: str = Field(..., description="Name of the file")
    creation_time: str = Field(..., description="File creation timestamp")
    line_count: int = Field(..., description="Number of lines in the file")

class FileListResponse(BaseModel):
    """
    Response containing list of file information
    """
    files: List[FileInfo] = Field(..., description="List of file information")
