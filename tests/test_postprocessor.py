"""Unit tests for DocumentPostprocessor tabular reconciliation and entity consolidation."""

from src.schemas.document import (
    CENSORED_SENTINEL,
    BlockType,
    DocumentBlock,
    HeaderMetadataPayload,
    IdentityCredentialPayload,
    PageExtraction,
    StampSignaturePayload,
    TablePayload,
    TableSplitMetadata,
    TableSplitType,
)
from src.services.postprocessor import DocumentPostprocessor


def test_vertical_table_stitching_multi_page():
    """Valida la unión de una tabla dividida verticalmente entre la página 1 y la página 2."""
    postprocessor = DocumentPostprocessor()

    # Página 1: Filas 1 y 2, se marca que continuará
    table_p1 = TablePayload(
        caption="Nómina General de Empleados",
        headers=["ID", "Nombre", "Departamento", "Sueldo"],
        rows=[
            ["001", "Ana Gómez", "Finanzas", "$2500"],
            ["002", "Juan Soto", "TI", "$3000"],
        ],
        split_metadata=TableSplitMetadata(
            table_id="table_emp_1",
            has_subsequent_continuation=True,
        ),
    )

    page_1 = PageExtraction(
        page_number=1,
        blocks=[
            DocumentBlock(
                reading_order_index=1,
                block_type=BlockType.TABLE,
                table_data=table_p1,
            )
        ],
    )

    # Página 2: Filas 3 y 4, continúa formalmente de table_emp_1
    table_p2 = TablePayload(
        caption="Nómina (Continuación Página 2)",
        headers=["ID", "Nombre", "Departamento", "Sueldo"],
        rows=[
            ["003", "Carlos Silva", "Ventas", "$2200"],
            ["004", "Elena Torres", "Operaciones", "$2800"],
        ],
        split_metadata=TableSplitMetadata(
            table_id="table_emp_1_part2",
            is_continuation=True,
            continuation_of_id="table_emp_1",
            split_type=TableSplitType.VERTICAL_CONTINUATION,
            has_subsequent_continuation=False,
        ),
    )

    page_2 = PageExtraction(
        page_number=2,
        blocks=[
            DocumentBlock(
                reading_order_index=1,
                block_type=BlockType.TABLE,
                table_data=table_p2,
            )
        ],
    )

    result = postprocessor.process("doc-123", "nomina.pdf", [page_1, page_2])

    assert len(result.unified_tables) == 1
    unified = result.unified_tables[0]
    assert unified.split_metadata.table_id == "table_emp_1"
    assert len(unified.rows) == 4
    assert unified.rows[0][1] == "Ana Gómez"
    assert unified.rows[2][1] == "Carlos Silva"
    assert unified.rows[3][1] == "Elena Torres"
    assert unified.split_metadata.has_subsequent_continuation is False


def test_horizontal_table_stitching_columns():
    """Valida la unión de una tabla dividida horizontalmente (columnas partidas en bloque inferior)."""
    postprocessor = DocumentPostprocessor()

    # Bloque 1: Columnas iniciales
    table_left = TablePayload(
        caption="Matriz de Evaluación",
        headers=["RUT", "Nombre"],
        rows=[
            ["11.111.111-1", "Persona A"],
            ["22.222.222-2", "Persona B"],
        ],
        split_metadata=TableSplitMetadata(table_id="table_eval_1"),
    )

    # Bloque 2: Columnas extendidas que continúan a table_eval_1
    table_right = TablePayload(
        caption="Matriz de Evaluación (Columnas de Puntaje)",
        headers=["Puntaje Técnico", "Resultado Final"],
        rows=[
            ["95/100", "Aprobado"],
            ["82/100", "Aprobado"],
        ],
        split_metadata=TableSplitMetadata(
            table_id="table_eval_1_cols",
            is_continuation=True,
            continuation_of_id="table_eval_1",
            split_type=TableSplitType.HORIZONTAL_CONTINUATION,
        ),
    )

    page = PageExtraction(
        page_number=1,
        blocks=[
            DocumentBlock(reading_order_index=1, block_type=BlockType.TABLE, table_data=table_left),
            DocumentBlock(reading_order_index=2, block_type=BlockType.TABLE, table_data=table_right),
        ],
    )

    result = postprocessor.process("doc-eval", "evaluacion.pdf", [page])

    assert len(result.unified_tables) == 1
    unified = result.unified_tables[0]
    assert unified.headers == ["RUT", "Nombre", "Puntaje Técnico", "Resultado Final"]
    assert len(unified.rows) == 2
    assert unified.rows[0] == ["11.111.111-1", "Persona A", "95/100", "Aprobado"]
    assert unified.rows[1] == ["22.222.222-2", "Persona B", "82/100", "Aprobado"]


def test_heuristic_vertical_continuation_without_explicit_id():
    """Valida que la heurística de resiliencia fusione tablas si la anterior quedó abierta con mismas columnas."""
    postprocessor = DocumentPostprocessor()

    table_p1 = TablePayload(
        caption="Tabla de Gastos",
        headers=["Item", "Monto"],
        rows=[["Papelería", "$50"]],
        split_metadata=TableSplitMetadata(
            table_id="t1",
            has_subsequent_continuation=True,
        ),
    )

    # El LLM marcó is_continuation=True pero olvidó o equivocó continuation_of_id
    table_p2 = TablePayload(
        caption="Gastos Cont.",
        headers=["Item", "Monto"],
        rows=[["Transporte", "$120"]],
        split_metadata=TableSplitMetadata(
            table_id="t2",
            is_continuation=True,
            continuation_of_id=None,
        ),
    )

    p1 = PageExtraction(page_number=1, blocks=[DocumentBlock(reading_order_index=1, block_type=BlockType.TABLE, table_data=table_p1)])
    p2 = PageExtraction(page_number=2, blocks=[DocumentBlock(reading_order_index=1, block_type=BlockType.TABLE, table_data=table_p2)])

    result = postprocessor.process("doc-gastos", "gastos.pdf", [p1, p2])

    assert len(result.unified_tables) == 1
    assert len(result.unified_tables[0].rows) == 2
    assert result.unified_tables[0].rows[1][0] == "Transporte"


def test_censorship_detection_and_column_padding_defense():
    """Valida detección de censura y defensa ante filas incompletas en tablas continuadas."""
    postprocessor = DocumentPostprocessor()

    table_p1 = TablePayload(
        caption="Contrato Confidencial",
        headers=["Cláusula", "Monto", "Beneficiario"],
        rows=[
            ["1.1", "$100.000", "Empresa X"],
        ],
        split_metadata=TableSplitMetadata(table_id="t_conf", has_subsequent_continuation=True),
    )

    # Fila con celda censurada y menos columnas de las esperadas
    table_p2 = TablePayload(
        caption="Contrato Confidencial Cont.",
        headers=["Cláusula", "Monto", "Beneficiario"],
        rows=[
            ["1.2", CENSORED_SENTINEL],  # Falta la 3ra columna (debe rellenarse con None)
        ],
        split_metadata=TableSplitMetadata(
            table_id="t_conf_part2",
            is_continuation=True,
            continuation_of_id="t_conf",
        ),
    )

    p1 = PageExtraction(page_number=1, blocks=[DocumentBlock(reading_order_index=1, block_type=BlockType.TABLE, table_data=table_p1)])
    p2 = PageExtraction(page_number=2, blocks=[DocumentBlock(reading_order_index=1, block_type=BlockType.TABLE, table_data=table_p2)])

    result = postprocessor.process("doc-censor", "confidencial.pdf", [p1, p2])

    assert result.has_censored_content is True
    assert len(result.unified_tables) == 1
    # Comprobar que la segunda fila fue acolchonada (padded) defensivamente sin arrojar IndexError
    assert len(result.unified_tables[0].rows[1]) == 3
    assert result.unified_tables[0].rows[1][1] == CENSORED_SENTINEL
    assert result.unified_tables[0].rows[1][2] is None


def test_credential_and_signature_aggregation_and_deduplication():
    """Valida la consolidación y deduplicación de credenciales y firmas multi-página."""
    postprocessor = DocumentPostprocessor()

    cred_1 = IdentityCredentialPayload(full_name="Pedro Soto", id_number="15.111.222-3")
    cred_duplicate = IdentityCredentialPayload(full_name="pedro soto", id_number="15.111.222-3")
    cred_2 = IdentityCredentialPayload(full_name="María Rojas", id_number="19.333.444-5")

    sig_1 = StampSignaturePayload(signer_name="Abogado Notario", has_stamp_or_seal=True)
    sig_2 = StampSignaturePayload(signer_name="Ministro de Fe", has_physical_signature=True)

    header = HeaderMetadataPayload(document_title="Certificado de Acreditación", folio_or_id="CERT-8877")

    p1 = PageExtraction(
        page_number=1,
        blocks=[
            DocumentBlock(reading_order_index=1, block_type=BlockType.HEADER_METADATA, header_data=header),
            DocumentBlock(reading_order_index=2, block_type=BlockType.IDENTITY_CREDENTIAL, credential_data=cred_1),
            DocumentBlock(reading_order_index=3, block_type=BlockType.STAMP_SIGNATURE, signature_data=sig_1),
        ],
    )

    p2 = PageExtraction(
        page_number=2,
        blocks=[
            DocumentBlock(reading_order_index=1, block_type=BlockType.IDENTITY_CREDENTIAL, credential_data=cred_duplicate),
            DocumentBlock(reading_order_index=2, block_type=BlockType.IDENTITY_CREDENTIAL, credential_data=cred_2),
            DocumentBlock(reading_order_index=3, block_type=BlockType.STAMP_SIGNATURE, signature_data=sig_2),
        ],
    )

    result = postprocessor.process("doc-cred", "credenciales.pdf", [p1, p2])

    assert result.global_metadata.document_title == "Certificado de Acreditación"
    assert result.global_metadata.folio_or_id == "CERT-8877"
    # Deduplicación de credenciales: Pedro Soto aparecía en p1 y p2 con mismo ID
    assert len(result.extracted_credentials) == 2
    ids = [c.id_number for c in result.extracted_credentials]
    assert "15.111.222-3" in ids
    assert "19.333.444-5" in ids
    # Firmas acumuladas
    assert len(result.extracted_signatures) == 2


def test_different_headers_rejected_as_independent_tables():
    """Valida el caso crítico de PRUEBA.pdf: tablas con encabezados incompatibles no deben fusionarse verticalmente."""
    postprocessor = DocumentPostprocessor()

    table_p1 = TablePayload(
        headers=["ID", "PRODUCTO", "NOMBRE"],
        rows=[
            ["1234", "AAA", "A"],
            ["2", "BBB", "B"],
            ["3", "CCC", "C"],
        ],
        split_metadata=TableSplitMetadata(
            table_id="table_1",
            is_continuation=False,
            has_subsequent_continuation=False,
        ),
    )

    # El LLM erróneamente marcó is_continuation=True hacia table_1
    table_p2 = TablePayload(
        headers=["PRECIO", "STOCK"],
        rows=[
            ["2", "1231"],
            ["1", "12312"],
            ["23", "124"],
        ],
        split_metadata=TableSplitMetadata(
            table_id="table_1",  # Mismo ID por alucinación del LLM
            is_continuation=True,
            continuation_of_id="table_1",
            split_type=TableSplitType.VERTICAL_CONTINUATION,
            has_subsequent_continuation=False,
        ),
    )

    p1 = PageExtraction(page_number=1, blocks=[DocumentBlock(reading_order_index=1, block_type=BlockType.TABLE, table_data=table_p1)])
    p2 = PageExtraction(page_number=2, blocks=[DocumentBlock(reading_order_index=1, block_type=BlockType.TABLE, table_data=table_p2)])

    result = postprocessor.process("doc-prueba", "PRUEBA.pdf", [p1, p2])

    # Deben resultar 2 tablas separadas e independientes
    assert len(result.unified_tables) == 2

    # Tabla 1: Productos
    t1 = result.unified_tables[0]
    assert t1.headers == ["ID", "PRODUCTO", "NOMBRE"]
    assert len(t1.rows) == 3
    assert t1.rows[0] == ["1234", "AAA", "A"]

    # Tabla 2: Precios y Stock (con ID único generado defensivamente)
    t2 = result.unified_tables[1]
    assert t2.headers == ["PRECIO", "STOCK"]
    assert len(t2.rows) == 3
    assert t2.rows[0] == ["2", "1231"]
    assert t2.split_metadata.table_id != t1.split_metadata.table_id
    assert t2.split_metadata.is_continuation is False


def test_vertical_continuation_without_repeated_headers():
    """Valida la continuación de una tabla cortada donde la página 2 no repite encabezados y arranca con datos."""
    postprocessor = DocumentPostprocessor()

    table_p1 = TablePayload(
        caption="Inventario Parte 1",
        headers=["SKU", "Descripción", "Ubicación"],
        rows=[
            ["A01", "Tornillo 3mm", "Estante 1"],
            ["A02", "Tuerca 3mm", "Estante 1"],
        ],
        split_metadata=TableSplitMetadata(
            table_id="t_inv",
            has_subsequent_continuation=True,
        ),
    )

    # La página 2 arranca directamente con filas sin encabezados reales (o inferidos Col_1, Col_2...)
    table_p2 = TablePayload(
        caption=None,
        headers=["Col_1", "Col_2", "Col_3"],
        rows=[
            ["A03", "Arandela 3mm", "Estante 2"],
            ["A04", "Clavo 2pulg", "Estante 3"],
        ],
        split_metadata=TableSplitMetadata(
            table_id="t_inv_cont",
            is_continuation=True,
            continuation_of_id="t_inv",
            split_type=TableSplitType.VERTICAL_CONTINUATION,
        ),
    )

    p1 = PageExtraction(page_number=1, blocks=[DocumentBlock(reading_order_index=1, block_type=BlockType.TABLE, table_data=table_p1)])
    p2 = PageExtraction(page_number=2, blocks=[DocumentBlock(reading_order_index=1, block_type=BlockType.TABLE, table_data=table_p2)])

    result = postprocessor.process("doc-inv", "inventario.pdf", [p1, p2])

    assert len(result.unified_tables) == 1
    unified = result.unified_tables[0]
    assert unified.headers == ["SKU", "Descripción", "Ubicación"]
    assert len(unified.rows) == 4
    assert unified.rows[2] == ["A03", "Arandela 3mm", "Estante 2"]
    assert unified.rows[3] == ["A04", "Clavo 2pulg", "Estante 3"]


def test_vertical_continuation_with_fuzzy_matching_headers_and_dedup():
    """Valida fusión vertical con encabezados con tildes/espacios y deduplicación si el LLM extrajo el encabezado en row 0."""
    postprocessor = DocumentPostprocessor()

    table_p1 = TablePayload(
        headers=["CÓDIGO", "DESCRIPCIÓN", "MONTO NETO"],
        rows=[["C1", "Item A", "100"]],
        split_metadata=TableSplitMetadata(table_id="t_fact", has_subsequent_continuation=True),
    )

    # Página 2 repite encabezados con pequeñas diferencias de acento/espacio
    # y accidentalmente puso la fila de encabezados como fila 0 de rows
    table_p2 = TablePayload(
        headers=["codigo", "descripcion ", "monto neto"],
        rows=[
            ["CÓDIGO", "DESCRIPCIÓN", "MONTO NETO"],  # Fila duplicada por el OCR
            ["C2", "Item B", "200"],
        ],
        split_metadata=TableSplitMetadata(
            table_id="t_fact_p2",
            is_continuation=True,
            continuation_of_id="t_fact",
            split_type=TableSplitType.VERTICAL_CONTINUATION,
        ),
    )

    p1 = PageExtraction(page_number=1, blocks=[DocumentBlock(reading_order_index=1, block_type=BlockType.TABLE, table_data=table_p1)])
    p2 = PageExtraction(page_number=2, blocks=[DocumentBlock(reading_order_index=1, block_type=BlockType.TABLE, table_data=table_p2)])

    result = postprocessor.process("doc-fact", "factura.pdf", [p1, p2])

    assert len(result.unified_tables) == 1
    unified = result.unified_tables[0]
    # La fila duplicada de encabezados en row 0 debe haberse omitido
    assert len(unified.rows) == 2
    assert unified.rows[0] == ["C1", "Item A", "100"]
    assert unified.rows[1] == ["C2", "Item B", "200"]


def test_multiple_independent_tables_same_page():
    """Valida que dos tablas en la misma página sin relación se conserven de forma independiente."""
    postprocessor = DocumentPostprocessor()

    table_a = TablePayload(
        caption="Resumen de Ventas",
        headers=["Zona", "Ventas"],
        rows=[["Norte", "5000"], ["Sur", "3000"]],
        split_metadata=TableSplitMetadata(table_id="t_resumen"),
    )

    table_b = TablePayload(
        caption="Detalle de Gastos",
        headers=["Categoría", "Gasto"],
        rows=[["Viáticos", "800"], ["Insumos", "1200"]],
        split_metadata=TableSplitMetadata(table_id="t_gastos"),
    )

    p1 = PageExtraction(
        page_number=1,
        blocks=[
            DocumentBlock(reading_order_index=1, block_type=BlockType.TABLE, table_data=table_a),
            DocumentBlock(reading_order_index=2, block_type=BlockType.TABLE, table_data=table_b),
        ],
    )

    result = postprocessor.process("doc-same-page", "reporte.pdf", [p1])

    assert len(result.unified_tables) == 2
    assert result.unified_tables[0].split_metadata.table_id == "t_resumen"
    assert result.unified_tables[1].split_metadata.table_id == "t_gastos"


def test_horizontal_continuation_isolated_from_older_pages_with_same_local_id():
    """Valida que una continuación horizontal en la página 3 resuelva a la tabla de la misma página

    y no se fusione erróneamente con una tabla de la página 1 que compartía el mismo ID local ('table_2').
    """
    postprocessor = DocumentPostprocessor()

    # Página 1: table_1 e independiente table_2 (Precio y Stock)
    p1_t1 = TablePayload(
        headers=["ID", "PRODUCTO"],
        rows=[["PRD-01", "Servidor"]],
        split_metadata=TableSplitMetadata(table_id="table_1"),
    )
    p1_t2 = TablePayload(
        headers=["PRECIO_USD", "STOCK_DISPONIBLE", "UBICACIÓN_BODEGA"],
        rows=[["$ 3,450.00", "12", "Rack A"]],
        split_metadata=TableSplitMetadata(table_id="table_2"),
    )
    p1 = PageExtraction(
        page_number=1,
        blocks=[
            DocumentBlock(reading_order_index=1, block_type=BlockType.TABLE, table_data=p1_t1),
            DocumentBlock(reading_order_index=2, block_type=BlockType.TABLE, table_data=p1_t2),
        ],
    )

    # Página 3: tabla con ID local 'table_2' y continuación horizontal 'table_3' (continuation_of_id='table_2')
    p3_t2 = TablePayload(
        headers=["RUT", "NOMBRE", "CARGO"],
        rows=[["15.234.887-2", "Ricardo", "Cloud"]],
        split_metadata=TableSplitMetadata(table_id="table_2"),
    )
    p3_t3 = TablePayload(
        headers=["EVAL_Q1", "EVAL_Q2", "RESULTADO_GLOBAL"],
        rows=[["94.5%", "96.2%", "APROBADO"]],
        split_metadata=TableSplitMetadata(
            table_id="table_3",
            is_continuation=True,
            continuation_of_id="table_2",
            split_type=TableSplitType.HORIZONTAL_CONTINUATION,
        ),
    )
    p3 = PageExtraction(
        page_number=3,
        blocks=[
            DocumentBlock(reading_order_index=1, block_type=BlockType.TABLE, table_data=p3_t2),
            DocumentBlock(reading_order_index=2, block_type=BlockType.TABLE, table_data=p3_t3),
        ],
    )

    result = postprocessor.process("doc-cross-scope", "evaluacion.pdf", [p1, p3])

    # Deben existir exactamente 3 tablas unificadas:
    # 1. p1_t1 (2 columnas)
    # 2. p1_t2 (3 columnas) - INTOCADA, no debe tener columnas de evaluación
    # 3. p3_t2 + p3_t3 (6 columnas: RUT, NOMBRE, CARGO, EVAL_Q1, EVAL_Q2, RESULTADO_GLOBAL)
    assert len(result.unified_tables) == 3

    # Validar tabla 2 de la página 1 intacta
    t2_p1 = result.unified_tables[1]
    assert t2_p1.headers == ["PRECIO_USD", "STOCK_DISPONIBLE", "UBICACIÓN_BODEGA"]
    assert len(t2_p1.rows[0]) == 3

    # Validar tabla fusionada de la página 3 con sus 6 columnas unificadas
    t_unified_p3 = result.unified_tables[2]
    assert t_unified_p3.headers == ["RUT", "NOMBRE", "CARGO", "EVAL_Q1", "EVAL_Q2", "RESULTADO_GLOBAL"]
    assert len(t_unified_p3.rows[0]) == 6
    assert t_unified_p3.rows[0] == ["15.234.887-2", "Ricardo", "Cloud", "94.5%", "96.2%", "APROBADO"]

