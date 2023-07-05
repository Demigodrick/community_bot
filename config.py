import os
from pydantic.env_settings import BaseSettings


class Settings(BaseSettings):
    USERNAME: str
    PASSWORD: str
    BOT_ID: int
    INSTANCE: str
    COMMUNITY: str
    SCORE: int
    LOCAL: bool

    class Config:
        env_file = ".env"

os.environ.pop("USERNAME", None)
os.environ.pop("PASSWORD", None)

settings = Settings()
