"""Comprehensive tests for VisionExtractorService, LCEL chains, and security defenses."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import SecretStr

from src.core.config import Settings
from src.schemas.document import (
    CENSORED_SENTINEL,
    BlockType,
    DocumentBlock,
    HeaderMetadataPayload,
    IdentityCredentialPayload,
    PageExtraction,
    TablePayload,
    TableSplitMetadata,
    TextParagraphPayload,
)
from src.services.vision_extractor import (
    SYSTEM_INSTRUCTION_PROMPT,
    ExtractionModelError,
    OpenAIConfigurationError,
    PreviousPageContext,
    VisionExtractorService,
)

# =====================================================================
# Pruebas de Seguridad y Configuración
# =====================================================================


def test_missing_api_key_raises_configuration_error():
    """Valida que la ausencia de API Key detenga la ejecución de forma Fail-Fast."""
    empty_settings = Settings(
        OPENAI_API_KEY=SecretStr(""),
        GEMINI_API_KEY=SecretStr(""),
        GOOGLE_API_KEY=SecretStr(""),
        _env_file=None,
    )
    service = VisionExtractorService(model_name="gpt-4o")

    with patch("src.services.vision_extractor.settings", empty_settings):
        with pytest.raises(OpenAIConfigurationError) as exc_info:
            service._get_llm()
        assert "OPENAI_API_KEY no está configurada" in str(exc_info.value)


def test_get_llm_configures_reasoning_effort_for_gpt5():
    """Valida que para la familia gpt-5.6-terra se configure reasoning_effort en ChatOpenAI."""
    settings_gpt5 = Settings(
        OPENAI_API_KEY=SecretStr("sk-test-fake-key-12345"),
        OPENAI_MODEL="gpt-5.6-terra",
        OPENAI_REASONING_EFFORT="medium",
        _env_file=None,
    )
    service = VisionExtractorService(model_name="gpt-5.6-terra")

    with patch("src.services.vision_extractor.settings", settings_gpt5):
        llm = service._get_llm()
        assert llm.model_name == "gpt-5.6-terra"
        assert getattr(llm, "reasoning_effort", None) == "medium"


def test_get_llm_configures_temperature_for_gpt4o():
    """Valida que para modelos tradicionales como gpt-4o se utilice temperature."""
    settings_gpt4 = Settings(
        OPENAI_API_KEY=SecretStr("sk-test-fake-key-12345"),
        OPENAI_MODEL="gpt-4o",
        _env_file=None,
    )
    service = VisionExtractorService(model_name="gpt-4o", temperature=0.0)

    with patch("src.services.vision_extractor.settings", settings_gpt4):
        llm = service._get_llm()
        assert llm.model_name == "gpt-4o"
        assert llm.temperature == 0.0
        assert getattr(llm, "reasoning_effort", None) is None


def test_get_llm_configures_gemini():
    """Valida la instanciación de ChatGoogleGenerativeAI para modelos Gemini."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    settings_gemini = Settings(
        GEMINI_API_KEY=SecretStr("fake-gemini-key"),
        OPENAI_MODEL="gemini-3.8-flash",
        _env_file=None,
    )
    service = VisionExtractorService(model_name="gemini-3.8-flash")

    with patch("src.services.vision_extractor.settings", settings_gemini):
        llm = service._get_llm()
        assert isinstance(llm, ChatGoogleGenerativeAI)
        assert llm.model == "gemini-3.8-flash"


def test_prompt_injection_defense_is_embedded():
    """Verifica que el prompt de sistema contenga directivas estrictas contra inyección de prompts."""
    assert "ADVERTENCIA DE SEGURIDAD ESTRICTA" in SYSTEM_INSTRUCTION_PROMPT
    assert "untrusted input" in SYSTEM_INSTRUCTION_PROMPT
    assert "IGNORA COMPLETAMENTE LA ORDEN" in SYSTEM_INSTRUCTION_PROMPT
    assert "Zero Hallucination" in SYSTEM_INSTRUCTION_PROMPT


def test_prompt_contains_all_edge_case_rules():
    """Verifica que el prompt instruya explícitamente sobre los 3 casos borde."""
    # Caso 1: Polimórficos
    assert "identity_credential" in SYSTEM_INSTRUCTION_PROMPT
    assert "stamp_signature" in SYSTEM_INSTRUCTION_PROMPT

    # Caso 2: Tablas continuadas
    assert "vertical_continuation" in SYSTEM_INSTRUCTION_PROMPT
    assert "has_subsequent_continuation" in SYSTEM_INSTRUCTION_PROMPT

    # Caso 3: Censura
    assert CENSORED_SENTINEL in SYSTEM_INSTRUCTION_PROMPT
    assert "NUNCA la omitas ni colapses la fila" in SYSTEM_INSTRUCTION_PROMPT


# =====================================================================
# Pruebas de Construcción del Mensaje Multimodal y Contexto
# =====================================================================


def test_build_multimodal_message_without_context():
    """Valida la generación de mensajes multimodales para la primera página."""
    service = VisionExtractorService()
    dummy_uri = "data:image/jpeg;base64,dGVzdA=="

    messages = service._build_multimodal_message(
        image_base64_uri=dummy_uri,
        page_number=1,
        total_pages=5,
        context=None,
    )

    assert len(messages) == 2
    # System Message
    assert messages[0].content == SYSTEM_INSTRUCTION_PROMPT
    # Human Message
    human_content = messages[1].content
    assert isinstance(human_content, list)
    assert human_content[0]["type"] == "text"
    assert "PÁGINA 1 de un total de 5" in human_content[0]["text"]
    assert human_content[1]["type"] == "image_url"
    assert human_content[1]["image_url"]["url"] == dummy_uri
    assert human_content[1]["image_url"]["detail"] == "high"


def test_build_multimodal_message_with_inherited_context():
    """Valida que tablas continuadas de la página previa se inyecten en el prompt de la siguiente."""
    service = VisionExtractorService()
    dummy_uri = "data:image/jpeg;base64,dGVzdA=="

    unclosed_table = TablePayload(
        caption="Facturación mensual",
        headers=["Item", "Descripción", "Monto"],
        rows=[["1", "Servicio Cloud", "$1200"]],
        split_metadata=TableSplitMetadata(
            table_id="table_billing_1",
            has_subsequent_continuation=True,
        ),
    )

    context = PreviousPageContext(
        previous_page_number=1,
        unclosed_tables=[unclosed_table],
        last_block_type="table",
    )

    messages = service._build_multimodal_message(
        image_base64_uri=dummy_uri,
        page_number=2,
        total_pages=5,
        context=context,
    )

    human_text = messages[1].content[0]["text"]
    assert "table_billing_1" in human_text
    assert "['Item', 'Descripción', 'Monto']" in human_text
    assert "quedó abierta en página 1" in human_text


# =====================================================================
# Pruebas de Ejecución de la Cadena LCEL con Mocks
# =====================================================================


def test_extract_page_sync_success_with_mock():
    """Valida la ejecución sincrónica de la cadena LCEL con un LLM mockeado."""
    expected_page = PageExtraction(
        page_number=1,
        blocks=[
            DocumentBlock(
                reading_order_index=1,
                block_type=BlockType.HEADER_METADATA,
                header_data=HeaderMetadataPayload(document_title="Contrato de Servicios"),
            ),
            DocumentBlock(
                reading_order_index=2,
                block_type=BlockType.IDENTITY_CREDENTIAL,
                credential_data=IdentityCredentialPayload(
                    full_name="Sebastián González",
                    id_number="18.999.888-K",
                ),
            ),
        ],
        page_summary="Página de cabecera con identificación",
    )

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = RunnableLambda(lambda _: expected_page)

    service = VisionExtractorService(llm_instance=mock_llm)
    result = service.extract_page(
        image_base64_uri="data:image/jpeg;base64,dGVzdA==",
        page_number=1,
        total_pages=1,
    )

    assert result.page_number == 1
    assert len(result.blocks) == 2
    assert result.blocks[0].header_data.document_title == "Contrato de Servicios"
    assert result.blocks[1].credential_data.id_number == "18.999.888-K"


@pytest.mark.asyncio
async def test_aextract_page_async_success_with_mock():
    """Valida la ejecución asíncrona (ainvoke) de la cadena LCEL."""
    expected_page = PageExtraction(
        page_number=2,
        blocks=[
            DocumentBlock(
                reading_order_index=1,
                block_type=BlockType.TEXT_PARAGRAPH,
                text_data=TextParagraphPayload(content="Texto extraído asíncronamente"),
            )
        ],
    )

    async def async_runner(_):
        return expected_page

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = RunnableLambda(async_runner)

    service = VisionExtractorService(llm_instance=mock_llm)
    result = await service.aextract_page(
        image_base64_uri="data:image/jpeg;base64,dGVzdA==",
        page_number=2,
        total_pages=3,
    )

    assert result.page_number == 2
    assert len(result.blocks) == 1
    assert result.blocks[0].text_data.content == "Texto extraído asíncronamente"


def test_page_number_normalization_if_model_returns_mismatch():
    """Valida que si el LLM devuelve un número de página incorrecto, el servicio lo normalice."""
    mismatched_page = PageExtraction(
        page_number=99,  # Mismatched
        blocks=[],
    )

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = RunnableLambda(lambda _: mismatched_page)

    service = VisionExtractorService(llm_instance=mock_llm)
    result = service.extract_page(
        image_base64_uri="data:image/jpeg;base64,dGVzdA==",
        page_number=3,
        total_pages=5,
    )

    assert result.page_number == 3  # Normalizado a la página real solicitada


def test_extraction_model_error_wraps_upstream_failures():
    """Valida que cualquier fallo de red o del LLM se envuelva en ExtractionModelError."""
    def failing_runner(_):
        raise RuntimeError("OpenAI 500 Internal Server Error")

    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = RunnableLambda(failing_runner)

    service = VisionExtractorService(llm_instance=mock_llm)

    with pytest.raises(ExtractionModelError) as exc_info:
        service.extract_page(
            image_base64_uri="data:image/jpeg;base64,dGVzdA==",
            page_number=1,
            total_pages=1,
        )

    assert "Fallo durante la invocación sincrónica del modelo" in str(exc_info.value)
