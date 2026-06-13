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

    # ASR
    asr_vendor: str = "baidu_rest"  # baidu_rest | xfyun
    asr_timeout: float = 60.0

    # 讯飞
    xfyun_appid: str = ""
    xfyun_apikey: str = ""
    xfyun_apisecret: str = ""

    # 百度实时 ASR
    baidu_app_id: str = "123686055"
    baidu_api_key: str = "PHz0LMhgVReOTlLvm4XhhY5C"
    baidu_secret_key: str = "XSHXjV1Pvk64StgptEDP40Ed8ao47Pdy"
    baidu_ws_url: str = "wss://vop.baidu.com/realtime_asr"
    baidu_dev_pid: str = "1537"  # 1537 普通话通用，按需要可改
    baidu_cuid: str = "ai_interpreter_windows"
    asr_timeout_seconds: float = 30.0

    ffmpeg_bin: str = "ffmpeg"

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    # Image generation (Qianfan)
    image_api_key: str = ""
    image_model: str = "qwen-image"
    image_timeout: float = 60.0

    # Database
    db_path: str = str(SQLITE_DB)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
