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
    SURVEY_CODE: str
    SLUR_ENABLED: bool
    SLUR_REGEX: str
    SERIOUS_WORDS: str
    MATRIX_FLAG: bool
    MATRIX_API_KEY: str
    MATRIX_ROOM_ID: str
    MATRIX_URL: str
    MATRIX_ACCOUNT: str
    ADMIN_ID: str


    class Config:
        env_file = ".env"

os.environ.pop("USERNAME", None)
os.environ.pop("PASSWORD", None)

settings = Settings()

