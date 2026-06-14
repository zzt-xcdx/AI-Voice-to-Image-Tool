from pydantic_settings import BaseSettings, SettingsConfigDict

from app.paths import ENV_FILE, SQLITE_DB


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_timeout: float = 60.0

    asr_timeout: float = 60.0
    baidu_api_key: str = ""
    baidu_secret_key: str = ""
    baidu_dev_pid: str = "1537"
    baidu_cuid: str = "ai_interpreter_windows"

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    image_api_key: str = ""
    image_model: str = "qwen-image"
    image_timeout: float = 60.0

    db_path: str = str(SQLITE_DB)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
