from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv("DATABASE_URL", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    whatsapp_api_key: str = os.getenv("WHATSAPP_API_KEY", "")
    whatsapp_webhook_token: str = os.getenv("WHATSAPP_WEBHOOK_TOKEN", "dora-verify-token")


settings = Settings()
