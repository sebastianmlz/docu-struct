"""Application configuration settings managed via Pydantic Settings."""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Carga variables del archivo .env a os.environ (esencial para LangChain/LangSmith tracing nativo)
load_dotenv(override=True)


class Settings(BaseSettings):
    """Global configuration settings following Twelve-Factor principles."""

    PROJECT_NAME: str = "DocuStruct - Heterogeneous Document Analyzer"
    VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Red y Enlace ASGI (0.0.0.0 requerido para contenedor Docker)
    HOST: str = "0.0.0.0"  # nosec B104
    PORT: int = 8000
    CORS_ORIGINS: str = Field(
        default="*",
        description="Orígenes permitidos para CORS (separados por coma o '*').",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Convierte la cadena de orígenes CORS a una lista limpia de strings."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # Proveedor y Modelo de IA
    LLM_PROVIDER: str = Field(
        default="auto",
        description="Proveedor forzado: 'google', 'openai' o 'auto' (detecta según el modelo o clave).",
    )
    OPENAI_MODEL: str = Field(
        default="gemini-3.8-flash",
        description="Modelo multimodal a invocar (e.g. 'gemini-3.8-flash', 'gpt-5.6-terra', 'gpt-4o').",
    )
    OPENAI_REASONING_EFFORT: str | None = Field(
        default="medium",
        description="Nivel de esfuerzo de pensamiento ('low', 'medium', 'high').",
    )

    # Credenciales de Google Gemini / AI Studio
    GEMINI_API_KEY: SecretStr = Field(
        default=SecretStr(""),
        description="API Key de Google Gemini (AI Studio).",
    )
    GOOGLE_API_KEY: SecretStr = Field(
        default=SecretStr(""),
        description="Alias estándar para la API Key de Google Gemini.",
    )

    # Credenciales de OpenAI
    OPENAI_API_KEY: SecretStr = Field(
        default=SecretStr(""),
        description="API Key de OpenAI.",
    )
    OPENAI_BASE_URL: str | None = Field(
        default=None,
        description="URL base personalizada para APIs compatibles con OpenAI (e.g. Ollama, vLLM, LM Studio en red local).",
    )

    # Restricciones de Ingesta
    MAX_UPLOAD_SIZE_MB: int = Field(
        default=25,
        ge=1,
        le=100,
        description="Tamaño máximo permitido en Megabytes para PDFs subidos.",
    )
    MAX_PAGES_PER_DOCUMENT: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Límite superior de páginas a procesar para mantener latencia controlada.",
    )

    # Pipeline Visual (pypdfium2)
    PDF_RENDER_DPI: int = Field(
        default=150,
        ge=72,
        le=300,
        description="Resolución de rasterizado. 150 DPI ofrece equilibrio óptimo entre tokens y OCR.",
    )
    MAX_PAGE_DIMENSION_POINTS: int = Field(
        default=5000,
        ge=500,
        le=15000,
        description="Dimensión máxima en puntos por página para neutralizar bombas de píxeles.",
    )

    # Hardening y Control de Recursos (Autónomo para Local/VPS)
    MAX_CONCURRENT_JOBS: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Máximo de documentos procesados simultáneamente para blindar la memoria RAM.",
    )
    RATE_LIMIT_PROCESS_PER_MINUTE: int = Field(
        default=10,
        ge=1,
        le=120,
        description="Límite de solicitudes de procesamiento por minuto por IP.",
    )
    PAGE_EXTRACTION_CONCURRENCY: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Máximo de páginas de un mismo documento procesadas concurrentemente por el modelo.",
    )
    DOCUMENT_TIMEOUT_SECONDS: int = Field(
        default=600,
        ge=10,
        le=1800,
        description="Límite de tiempo máximo en segundos para procesar un documento antes de timeout.",
    )
    STRICT_CSP_ENABLED: bool = Field(
        default=True,
        description="Activar Content-Security-Policy estricta en las cabeceras HTTP.",
    )

    # Observabilidad y Logging Estructurado
    JSON_LOGS_ENABLED: bool = Field(
        default=False,
        description="Activar salida de logs en formato JSON estructurado para entornos de producción/VPS.",
    )

    # Caché Idempotente en Memoria (RAM)
    CACHE_ENABLED: bool = Field(
        default=True,
        description="Activar caché en memoria por hash SHA-256 para evitar reprocesamiento y consumo duplicado de LLM.",
    )
    CACHE_MAX_ENTRIES: int = Field(
        default=50,
        ge=5,
        le=500,
        description="Número máximo de documentos extraídos retenidos simultáneamente en memoria (LRU).",
    )
    CACHE_TTL_SECONDS: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Tiempo de vida en segundos para las entradas en caché antes de expiración (1 hora por defecto).",
    )

    # Telemetría y Métricas (Formato Prometheus)
    METRICS_ENABLED: bool = Field(
        default=True,
        description="Habilitar endpoint /metrics en formato texto plano estándar de Prometheus.",
    )

    # Parada Ordenada (Graceful Shutdown)
    GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS: int = Field(
        default=15,
        ge=1,
        le=60,
        description="Tiempo máximo de espera en segundos para que los trabajos en vuelo finalicen antes del cierre.",
    )

    @property
    def max_upload_size_bytes(self) -> int:
        """Devuelve el límite de subida en bytes para validación temprana en FastAPI."""
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def effective_gemini_key(self) -> str:
        """Obtiene la clave activa de Google Gemini."""
        return (
            self.GEMINI_API_KEY.get_secret_value().strip()
            or self.GOOGLE_API_KEY.get_secret_value().strip()
        )

    @property
    def effective_openai_key(self) -> str:
        """Obtiene la clave activa de OpenAI o una clave placeholder para endpoints locales (Ollama/vLLM)."""
        key = self.OPENAI_API_KEY.get_secret_value().strip()
        if not key and self.OPENAI_BASE_URL:
            return "local-model-no-key-required"
        return key

    @property
    def is_gemini_configured(self) -> bool:
        return bool(self.effective_gemini_key)

    @property
    def is_openai_configured(self) -> bool:
        return bool(self.effective_openai_key) or bool(self.OPENAI_BASE_URL)

    def get_provider_for_model(self, model_name: str) -> str:
        """Determina el proveedor (google u openai) según el nombre del modelo o las claves."""
        m = model_name.lower().strip()
        if "gemini" in m:
            return "google"
        if any(m.startswith(p) for p in ("gpt", "o1", "o3", "o4")):
            return "openai"
        if self.LLM_PROVIDER != "auto":
            return self.LLM_PROVIDER.lower()
        if self.is_gemini_configured and not self.is_openai_configured:
            return "google"
        return "openai"

    @property
    def is_llm_configured(self) -> bool:
        provider = self.get_provider_for_model(self.OPENAI_MODEL)
        if provider == "google":
            return self.is_gemini_configured
        return self.is_openai_configured

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Singleton cacheado para las settings de la aplicación."""
    return Settings()


settings = get_settings()
