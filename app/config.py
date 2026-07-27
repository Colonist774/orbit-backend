from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Корневая папка зашифрованных вложений.
    # На сервере она должна быть подключена как постоянный volume.
    orbit_upload_dir: str = "uploads"

    max_image_size_mb: int = 10
    max_audio_size_mb: int = 25
    max_video_size_mb: int = 100

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
