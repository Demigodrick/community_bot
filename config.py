import os
from pydantic.env_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    USERNAME: str
    PASSWORD: str
    BOT_ID: int
    INSTANCE: str
    SCORE: int
    LOCAL: bool
    ADMIN_IDS: Optional[List[int]] = None

    @staticmethod
    def get_admin_ids() -> Optional[List[int]]:
        admin_id_env = os.getenv('ADMIN_ID')
        if admin_id_env is not None:
            return [int(id) for id in admin_id_env.split(',')]
        else:
            return None

    class Config:
        env_file = ".env"

os.environ.pop("USERNAME", None)
os.environ.pop("PASSWORD", None)

settings = Settings()
settings.ADMIN_IDS = settings.get_admin_ids()
