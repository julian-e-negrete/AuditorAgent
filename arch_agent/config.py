from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Agent configuration loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # LLM provider settings
    LLM_PROVIDER: str
    LLM_API_KEY: str
    LLM_MODEL: str = "gpt-4o"

    # GLPI proxy settings
    GLPI_PROXY_URL: str = "http://100.112.16.115:8080"
    GLPI_CLIENT_ID: str
    GLPI_CLIENT_SECRET: str
    GLPI_USERNAME: str
    GLPI_PASSWORD: str
    GLPI_SERVER_NAME: str = "SRV-GLPI-PROCESSOR"
