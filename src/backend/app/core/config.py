import os


def environment() -> str:
    return os.getenv("APP_ENV", "development").strip().lower()


def cors_origins() -> list[str]:
    value = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


def demo_auth_bypass_enabled() -> bool:
    requested = os.getenv("ALLOW_INSECURE_DEMO_AUTH", "false").lower() == "true"
    return requested and environment() in {"test", "demo"}
