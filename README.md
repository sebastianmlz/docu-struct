# DocuStruct

Microservicio y plataforma de extraccion estructurada y analisis forense para documentos PDF heterogeneos (1 a 10 paginas). Procesa documentos con tablas continuadas, coexistencia de credenciales de identidad, sellos, firmas manuscritas y datos censurados.

El sistema opera con rasterizado en memoria a 150 DPI mediante `pypdfium2`, inferencia multimodal con LangChain LCEL validada contra esquemas estrictos de Pydantic v2, y un motor determinista de reconciliacion tabular.

---

## Capacidades Principales

- **Reconciliacion de Tablas Continuadas:** Detecta tablas divididas a traves de multiples paginas y las unifica vertical u horizontalmente, preservando encabezados y compensando columnas ausentes.
- **Documentos Polimorficos:** Identifica y clasifica bloques de contenido en estricto orden de lectura visual (`reading_order_index`): membretes, parrafos de texto, credenciales de identidad (DNI/RUN), tablas y firmas con timbres institucionales.
- **Deteccion de Datos Censurados:** Identifica tachaduras, trazos de marcador o cintas correctoras, asignando el centinela `[DATO_CENSURADO]` sin alterar la alineacion ni cantidad de columnas de las filas afectadas.
- **Procesamiento en Memoria (Zero Disk I/O):** Las paginas del PDF se convierten a buffers de imagen en RAM, liberando los manejadores C++ inmediatamente para evitar fugas de memoria.

---

## Arquitectura del Proyecto

```text
docu-struct/
├── .github/workflows/
│   ├── ci.yml                 # Lint (Ruff), seguridad AST (Bandit), Pytest (3.10/3.11), smoke test Docker
│   └── cd.yml                 # Buildx, escaneo de vulnerabilidades Trivy y publicacion en GHCR
├── src/
│   ├── main.py                # Entrypoint ASGI FastAPI, middleware X-Request-ID, telemetria y CSP
│   ├── core/
│   │   ├── config.py          # Configuracion Pydantic Settings (Twelve-Factor, SecretStr)
│   │   ├── logging.py         # Logging estructurado JSON y correlacion con request_id
│   │   ├── cache.py           # Cache idempotente en RAM indexada por SHA-256 (LRU + TTL)
│   │   ├── telemetry.py       # Registro de metricas en memoria y exportador Prometheus
│   │   └── security.py        # Magic bytes, rate limiter, concurrency guard y graceful shutdown
│   ├── schemas/
│   │   ├── document.py        # Modelos Pydantic v2: PageExtraction, TablePayload, DocumentBlock
│   │   └── api_response.py    # Envelope estandar de respuesta HTTP y metricas de ejecucion
│   ├── services/
│   │   ├── pdf_converter.py   # Rasterizador de PDF a PNG en memoria (pypdfium2)
│   │   ├── vision_extractor.py# Cadena multimodal LCEL con reintentos exponenciales y jitter
│   │   └── postprocessor.py   # Motor algoritmico de union de tablas y deduplicacion
│   ├── api/
│   │   ├── router.py          # Enrutador central y endpoint /api/v1/health
│   │   └── v1/
│   │       └── documents.py   # Endpoint POST /api/v1/documents/process con verificacion de cache
│   ├── web/
│   │   ├── router.py          # Ruta GET / para la interfaz web
│   │   ├── templates/         # Plantilla Jinja2 con diseno forense e iconos vectoriales SVG
│   │   └── static/            # Cliente JavaScript nativo ES6 (sin dependencias Node.js)
│   └── utils/
│       └── image_utils.py     # Utilidades de codificacion Base64 y optimizacion de imagen
├── tests/                     # Suite de 81 pruebas automatizadas (unitarias, integracion, resiliencia)
├── Dockerfile                 # Imagen multi-stage de produccion con usuario no-root (appuser)
├── docker-compose.yml         # Orquestacion de contenedor con limites de CPU y memoria
├── pyproject.toml             # Configuracion de Ruff, Pytest y Coverage
└── requirements.txt           # Dependencias de produccion y herramientas de auditoria
```

---

## Requisitos Previos

- Python 3.10 o superior (si se ejecuta en local).
- Docker y Docker Compose (si se ejecuta en contenedor).
- Clave de API de Google Gemini (Google AI Studio) o clave de OpenAI.

---

## Configuracion de Variables de Entorno

Crear un archivo `.env` en la raiz del proyecto basado en `.env.example`:

```env
# Proveedor activo ('google' o 'openai')
LLM_PROVIDER=google

# Modelo multimodal a utilizar
OPENAI_MODEL=gemini-3.5-flash-lite

# Clave de Google AI Studio (si LLM_PROVIDER=google)
GEMINI_API_KEY=tu_clave_de_gemini_aqui

# Clave de OpenAI (si LLM_PROVIDER=openai)
OPENAI_API_KEY=tu_clave_de_openai_aqui
OPENAI_REASONING_EFFORT=medium

# Limites operativos
MAX_UPLOAD_SIZE_MB=25
MAX_PAGES_PER_DOCUMENT=10
PDF_RENDER_DPI=150

# Servidor ASGI
HOST=0.0.0.0
PORT=8000
DEBUG=False
CORS_ORIGINS=*
```

---

## Ejecucion Local

### 1. Crear y Activar Entorno Virtual

En Linux / macOS:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

En Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Iniciar Servidor de Desarrollo

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

- **Interfaz Web:** http://localhost:8000
- **Documentacion Interactiva OpenAPI:** http://localhost:8000/docs
- **Verificacion de Estado:** http://localhost:8000/api/v1/health

---

## Ejecucion con Docker

La imagen utiliza una construccion multi-stage sobre `python:3.10-slim-bookworm`, ejecutandose bajo el usuario de sistema `appuser` (UID 10001) sin privilegios de root.

### Con Docker Compose (Recomendado)

```bash
docker compose up -d --build
```

Para verificar logs:
```bash
docker compose logs -f docustruct
```

Para detener el servicio:
```bash
docker compose down
```

### Con Docker Directo

```bash
docker build -t docu-struct:latest .
docker run -d -p 8000:8000 --env-file .env --name docu-struct docu-struct:latest
```

---

## Calidad de Codigo y Pruebas Automatizadas

El proyecto incluye 51 pruebas automatizadas que cubren esquemas de datos, conversion de documentos, cadenas LCEL, reconciliacion tabular, endpoints HTTP y hardening de seguridad.

### Ejecutar Suite de Pruebas con Cobertura

```bash
pytest -v --cov=src --cov-report=term-missing
```

### Linteo de Codigo con Ruff

```bash
ruff check src/ tests/
```

### Auditoria Estatica de Seguridad con Bandit

```bash
bandit -r src/ -ll
```

---

## Pipeline de CI/CD (GitHub Actions)

El repositorio incluye dos flujos automatizados de integracion y entrega continua:

1. **`ci.yml` (Integracion Continua):**
   - Se activa ante cada `push` o `pull_request` hacia la rama `main`.
   - Ejecuta verificacion de formato y linteo con `ruff`.
   - Realiza analisis estatico de vulnerabilidades AST con `bandit`.
   - Corre la matriz completa de pruebas en Python 3.10 y 3.11 con reporte de cobertura.
   - Ejecuta un smoke test construyendo la imagen Docker y validando el endpoint de salud.

2. **`cd.yml` (Entrega Continua):**
   - Se activa ante etiquetas de version (`v*.*.*`) o despacho manual.
   - Compila la imagen con Docker Buildx y cache distribuido.
   - Analiza la imagen con **Trivy** en busca de CVEs criticos y exporta el reporte SARIF a GitHub Security.
   - Publica la imagen en **GitHub Container Registry (GHCR)** con versionado semantico.

---

## Especificacion de la API

### Ingestion y Procesamiento de Documentos
- **Metodo:** `POST /api/v1/documents/process`
- **Content-Type:** `multipart/form-data`
- **Parametros:** `file` (archivo PDF, maximo 10 paginas / 25 MB).
- **Respuesta (200 OK):** Objeto JSON estructurado conteniendo `document_id`, `unified_tables`, `extracted_credentials`, `extracted_signatures`, `global_metadata`, `pages` y `metrics`.

### Diagnostico de Salud
- **Metodo:** `GET /api/v1/health`
- **Respuesta (200 OK):** Estado operativo, version, proveedor activo, modelo LLM y limites configurados.

### Metricas y Telemetria Prometheus
- **Metodo:** `GET /metrics`
- **Respuesta (200 OK):** Texto plano compatible con Prometheus (v0.0.4) con contadores de peticiones, aciertos de cache, medidores de concurrencia y distribucion de latencia.

### Telemetria Operacional JSON
- **Metodo:** `GET /api/v1/telemetry`
- **Respuesta (200 OK):** Resumen de estado operativo en formato JSON (uptime, concurrencia activa, ratio de aciertos de cache y peticiones).

---

## Licencia

Este proyecto se distribuye bajo terminos de uso privado para practicas de ingenieria y desarrollo de software industrial.
