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
    practitioner_pin: str = os.getenv("PRACTITIONER_PIN", "1234")
    google_service_account_json: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    google_calendar_id: str = os.getenv("GOOGLE_CALENDAR_ID", "")
    google_oauth_client_id: str = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    google_oauth_client_secret: str = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    google_oauth_redirect_uri: str = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "")


settings = Settings()
