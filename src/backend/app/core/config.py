# backend/app/core/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    frontend_url: str = "http://localhost:5173"


settings = Settings()
