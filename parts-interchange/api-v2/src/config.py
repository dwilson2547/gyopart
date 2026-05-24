from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://parts_user:parts_pass@localhost:5432/parts_interchange"
    admin_api_key: str = "changeme-admin"
    worker_api_key: str = "changeme-worker"
    iggy_connection_string: str = "iggy+tcp://iggy:iggy@localhost:8090"
    iggy_stream: str = "parts-interchange"
    iggy_scrape_topic: str = "scrape-jobs"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
