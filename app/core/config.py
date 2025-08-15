from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "BrowserAutomationMCP"
    APP_VERSION: str = "0.1.0"
    DEBUG_MODE: bool = False

    # Security Settings
    SECRET_KEY: str = "super-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Browser Automation Settings
    MAX_BROWSER_INSTANCES: int = 2
    MAX_CONTEXTS_PER_BROWSER: int = 10
    MAX_CONCURRENT_SESSIONS: int = 20
    BROWSER_HEADLESS: bool = True
    BROWSER_TIMEOUT: int = 30000 # milliseconds

    # Redis Settings for Rate Limiting and Caching
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # Logging Settings
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "app.log"

settings = Settings()


