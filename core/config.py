from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    TELEGRAM_TOKEN: str
    DB_URL: str
    ADMIN_IDS: list[int] = [6095810791]
    
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

settings = Settings()
