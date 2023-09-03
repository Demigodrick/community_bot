import os
from pydantic.env_settings import BaseSettings

class Settings(BaseSettings):
    USERNAME: str
    PASSWORD: str
    BOT_ID: int
    INSTANCE: str
    SCORE: int
    LOCAL: bool
    EMAIL_FUNCTION: bool
    SMTP_SERVER: str
    SMTP_PORT: int
    SENDER_EMAIL: str
    SENDER_PASSWORD: str


    class Config:
        env_file = ".env"

os.environ.pop("USERNAME", None)
os.environ.pop("PASSWORD", None)

settings = Settings()

