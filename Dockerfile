# ==============================================================================
# DocuStruct - Multi-Stage Production Dockerfile
# Minimal attack surface, Non-root user, Native Healthcheck, Zero Temp Disk Write
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Build Dependencies & Wheels
# ------------------------------------------------------------------------------
FROM python:3.10-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Crear un entorno virtual aislado para copiar limpiamente al runner
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# ------------------------------------------------------------------------------
# Stage 2: Minimal Non-Root Production Runtime
# ------------------------------------------------------------------------------
FROM python:3.10-slim-bookworm AS runner

LABEL maintainer="DocuStruct Core Team" \
      description="Industrial-grade Heterogeneous Document Analyzer Microservice" \
      version="0.1.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HOST=0.0.0.0 \
    PORT=8000

# Instalar curl para healthchecks y certificados actualizados
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Hardening de Seguridad: Crear usuario y grupo de sistema sin privilegios ni shell
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -M appuser

WORKDIR /app

# Copiar el entorno virtual pre-compilado desde el builder
COPY --from=builder --chown=appuser:appgroup /opt/venv /opt/venv

# Copiar el código de la aplicación y recursos estáticos
COPY --chown=appuser:appgroup src/ ./src/

# Cambiar al usuario sin privilegios
USER appuser:appgroup

# Puerto de escucha del microservicio
EXPOSE 8000

# Healthcheck nativo contra el endpoint de diagnóstico
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/api/v1/health || exit 1

# Comando de ejecución con Uvicorn en modo producción
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
