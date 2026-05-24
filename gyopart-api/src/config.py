from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    parts_database_url: str
    inventory_api_url: str = "http://localhost:8000"
    inventory_api_timeout: float = 10.0
    cors_origins: str = "http://localhost:5173"

    model_config = {"env_file": ".env"}


settings = Settings()
