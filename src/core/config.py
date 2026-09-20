"""Application configuration settings managed via Pydantic Settings."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        """Obtiene la clave activa de OpenAI."""
        return self.OPENAI_API_KEY.get_secret_value().strip()

    @property
    def is_gemini_configured(self) -> bool:
        return bool(self.effective_gemini_key)

    @property
    def is_openai_configured(self) -> bool:
        return bool(self.effective_openai_key)

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
