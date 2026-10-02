from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    SALT_PERSON_SECRET: str
    SALT_VEHICLE_SECRET: str

    ENABLE_IP_WHITELIST: bool = False
    ALLOWED_SUBNETS: str = "10.20.0.0/16"

    REDIS_URL: str = "redis://localhost:6379/0"

    PANDASAI_LLM_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    FERNET_KEY: str = ""

    ENVIRONMENT: str = "development"


    @property
    def allowed_subnets_list(self) -> List[str]:
        return [s.strip() for s in self.ALLOWED_SUBNETS.split(",")]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


settings = Settings()
