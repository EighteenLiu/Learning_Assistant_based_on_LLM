import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("JWT_SECRET", "dev-only-secret-key-change-me")
DEBUG = os.getenv("DEBUG", "1") == "1"

ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "learning",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "app.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "app.wsgi.application"
ASGI_APPLICATION = "app.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Bilingual Learning Platform API",
    "DESCRIPTION": "基于LLM的双语课程辅助学习平台后端接口",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

def _env_bool(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default) or "").strip().lower() in {"1", "true", "yes", "on"}


USE_LOCAL_LLM = _env_bool("USE_LOCAL_LLM", "0")

if USE_LOCAL_LLM:
    OPENAI_BASE_URL = str(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1") or "").strip().rstrip("/")
    OPENAI_API_KEY = str(os.getenv("OLLAMA_API_KEY") or os.getenv("OPENAI_API_KEY") or "ollama").strip()
    OPENAI_MODEL = str(os.getenv("OLLAMA_MODEL", "qwen2.5vl:3b") or "").strip()
else:
    OPENAI_BASE_URL = str(os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1") or "").strip().rstrip("/")
    OPENAI_API_KEY = str(os.getenv("OPENAI_API_KEY", "") or "").strip()
    OPENAI_MODEL = str(os.getenv("OPENAI_MODEL", "qwen-plus") or "").strip()

TRANSLATION_MAX_WORKERS = max(int(os.getenv("TRANSLATION_MAX_WORKERS", "1") or 1), 1)
TRANSLATION_CHUNK_MAX_CONTAINERS = max(int(os.getenv("TRANSLATION_CHUNK_MAX_CONTAINERS", "6") or 1), 1)
TRANSLATION_CHUNK_MAX_CHARS = max(int(os.getenv("TRANSLATION_CHUNK_MAX_CHARS", "2000") or 200), 200)
TRANSLATION_CHUNK_MAX_RETRIES = max(int(os.getenv("TRANSLATION_CHUNK_MAX_RETRIES", "2") or 1), 1)

LLM_REQUEST_MAX_RETRIES = max(int(os.getenv("LLM_REQUEST_MAX_RETRIES", "3") or 1), 1)
LLM_REQUEST_RETRY_BASE_DELAY = max(float(os.getenv("LLM_REQUEST_RETRY_BASE_DELAY", "0.2") or 0.1), 0.1)
LLM_REQUEST_TIMEOUT_SECONDS = max(float(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "180") or 5), 5)
TRANSLATION_IMAGE_OCR_ENABLED = os.getenv("TRANSLATION_IMAGE_OCR_ENABLED", "1") == "1"
TRANSLATION_IMAGE_OCR_MAX_CONTAINERS_PER_SLIDE = max(
    int(os.getenv("TRANSLATION_IMAGE_OCR_MAX_CONTAINERS_PER_SLIDE", "3") or 1),
    1,
)
TRANSLATION_IMAGE_OCR_MIN_AREA_RATIO = max(
    float(os.getenv("TRANSLATION_IMAGE_OCR_MIN_AREA_RATIO", "0.015") or 0.001),
    0.001,
)
TRANSLATION_LONG_PAGE_CHAR_THRESHOLD = max(
    int(os.getenv("TRANSLATION_LONG_PAGE_CHAR_THRESHOLD", "1800") or 200),
    200,
)
TRANSLATION_LONG_PAGE_MAX_FONT_SIZE = max(
    int(os.getenv("TRANSLATION_LONG_PAGE_MAX_FONT_SIZE", "9") or 6),
    6,
)
PDF_RENDER_DPI = max(int(os.getenv("PDF_RENDER_DPI", "144") or 72), 72)

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", str(BASE_DIR / "chroma_db"))
