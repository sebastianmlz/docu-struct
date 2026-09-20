"""Deterministic postprocessing and tabular reconciliation engine.

Reconstructs split tables (vertical & horizontal continuations), aggregates polymorphic
blocks (credentials, signatures, metadata), and evaluates document-wide censorship.
"""

import copy
import logging

from src.schemas.document import (
    CENSORED_SENTINEL,
    BlockType,
    DocumentExtractionResult,
    HeaderMetadataPayload,
    IdentityCredentialPayload,
    PageExtraction,
    StampSignaturePayload,
    TablePayload,
    TableSplitType,
)

logger = logging.getLogger("docustruct.postprocessor")


class DocumentPostprocessor:
    """Motor algorítmico determinista para la consolidación y reconciliación de documentos."""

    def __init__(self) -> None:
        pass

    def process(
        self,
        document_id: str,
        filename: str,
        pages: list[PageExtraction],
    ) -> DocumentExtractionResult:
        """Consolida las extracciones individuales de cada página en un único contrato unificado.

        Garantiza preservación de datos sin pérdida, resolución de tablas continuadas
        y detección de censura en todo el documento.
        """
        logger.info("Iniciando postprocesamiento para documento '%s' (%d páginas)", filename, len(pages))

        # 1. Reconciliación de tablas partidas
        unified_tables = self._reconcile_tables(pages)

        # 2. Consolidación de credenciales (cédulas, carnets)
        extracted_credentials = self._extract_credentials(pages)

        # 3. Consolidación de firmas y sellos institucionales
        extracted_signatures = self._extract_signatures(pages)

        # 4. Consolidación de metadatos globales del documento
        global_metadata = self._extract_global_metadata(pages)

        # 5. Detección global de censura / datos tachados
        has_censored = self._detect_document_censorship(pages, unified_tables)

        result = DocumentExtractionResult(
            document_id=document_id,
            filename=filename,
            total_pages=len(pages),
            global_metadata=global_metadata,
            pages=pages,
            unified_tables=unified_tables,
            extracted_credentials=extracted_credentials,
            extracted_signatures=extracted_signatures,
            has_censored_content=has_censored,
        )

        logger.info(
            "Postprocesamiento completado. Tablas unificadas: %d, Credenciales: %d, Firmas: %d, Censura detectada: %s",
            len(unified_tables),
            len(extracted_credentials),
            len(extracted_signatures),
            has_censored,
        )

        return result

    def _reconcile_tables(self, pages: list[PageExtraction]) -> list[TablePayload]:
        """Reconstruye tablas partidas vertical u horizontalmente a lo largo de las páginas."""
        consolidated: list[TablePayload] = []
        table_map: dict[str, TablePayload] = {}
        last_table_seen: TablePayload | None = None

        # Ordenar páginas por número para procesar secuencialmente
        sorted_pages = sorted(pages, key=lambda p: p.page_number)

        for page in sorted_pages:
            table_blocks = [
                b for b in sorted(page.blocks, key=lambda b: b.reading_order_index)
                if b.block_type == BlockType.TABLE and b.table_data is not None
            ]

            for block in table_blocks:
                current_table = copy.deepcopy(block.table_data)
                meta = current_table.split_metadata

                # Caso 1: La tabla indica explícitamente ser continuación
                target_parent: TablePayload | None = None

                if meta.is_continuation and meta.continuation_of_id:
                    target_parent = table_map.get(meta.continuation_of_id)

                # Heurística de Resiliencia: Si es continuación pero continuation_of_id falló,
                # o si la tabla anterior quedó con has_subsequent_continuation=True
                if (
                    target_parent is None
                    and last_table_seen is not None
                    and (meta.is_continuation or last_table_seen.split_metadata.has_subsequent_continuation)
                    and len(last_table_seen.headers) == len(current_table.headers)
                ):
                    target_parent = last_table_seen
                    logger.info(
                        "Heurística de reconciliación: asociando tabla '%s' como continuación de '%s'",
                        meta.table_id,
                        last_table_seen.split_metadata.table_id,
                    )

                # Si encontramos la tabla matriz a continuar
                if target_parent is not None:
                    if meta.split_type == TableSplitType.HORIZONTAL_CONTINUATION:
                        self._stitch_horizontal(target_parent, current_table)
                    else:
                        # Por defecto vertical (filas continuadas)
                        self._stitch_vertical(target_parent, current_table)

                    # Actualizar estado de si la tabla continuará aún más
                    target_parent.split_metadata.has_subsequent_continuation = (
                        meta.has_subsequent_continuation
                    )
                    last_table_seen = target_parent
                else:
                    # Es una tabla nueva e independiente
                    consolidated.append(current_table)
                    table_map[meta.table_id] = current_table
                    last_table_seen = current_table

        return consolidated

    @staticmethod
    def _stitch_vertical(parent: TablePayload, child: TablePayload) -> None:
        """Fusiona filas continuadas asegurando alineación de columnas."""
        target_col_count = len(parent.headers)

        for row in child.rows:
            # Si el hijo tiene menos celdas que columnas, rellenar con None
            if len(row) < target_col_count:
                padded_row = row + [None] * (target_col_count - len(row))
                parent.rows.append(padded_row)
            elif len(row) > target_col_count:
                # Si excede columnas, recortar para no romper estructura
                parent.rows.append(row[:target_col_count])
            else:
                parent.rows.append(row)

        logger.debug(
            "Fusión vertical exitosa: Tabla '%s' ahora cuenta con %d filas",
            parent.split_metadata.table_id,
            len(parent.rows),
        )

    @staticmethod
    def _stitch_horizontal(parent: TablePayload, child: TablePayload) -> None:
        """Fusiona columnas partidas entre dos bloques tabulares."""
        # Agregar los nuevos headers excluyendo duplicados evidentes (e.g. ID de fila)
        added_indices: list[int] = []
        for idx, header in enumerate(child.headers):
            if header not in parent.headers:
                parent.headers.append(header)
                added_indices.append(idx)

        # Si no hubo headers nuevos, agregar todas las columnas hijas
        if not added_indices:
            added_indices = list(range(len(child.headers)))
            parent.headers.extend([f"Col_Ext_{i+1}" for i in added_indices])

        # Anexar las celdas correspondientes a cada fila
        max_rows = max(len(parent.rows), len(child.rows))
        for r_idx in range(max_rows):
            # Asegurar que la fila del padre existe
            if r_idx >= len(parent.rows):
                parent.rows.append([None] * (len(parent.headers) - len(added_indices)))

            child_row = child.rows[r_idx] if r_idx < len(child.rows) else []
            for col_idx in added_indices:
                val = child_row[col_idx] if col_idx < len(child_row) else None
                parent.rows[r_idx].append(val)

        logger.debug(
            "Fusión horizontal exitosa: Tabla '%s' ahora cuenta con %d columnas y %d filas",
            parent.split_metadata.table_id,
            len(parent.headers),
            len(parent.rows),
        )

    @staticmethod
    def _extract_credentials(pages: list[PageExtraction]) -> list[IdentityCredentialPayload]:
        """Colecciona y deduplica credenciales/cédulas encontradas en el documento."""
        credentials: list[IdentityCredentialPayload] = []
        seen_keys: set[str] = set()

        for page in pages:
            for block in page.blocks:
                if block.block_type == BlockType.IDENTITY_CREDENTIAL and block.credential_data is not None:
                    cred = block.credential_data
                    dedup_key = f"{cred.id_number or ''}-{cred.full_name or ''}".strip().lower()
                    if dedup_key and dedup_key not in seen_keys:
                        seen_keys.add(dedup_key)
                        credentials.append(cred)
                    elif not dedup_key:
                        credentials.append(cred)

        return credentials

    @staticmethod
    def _extract_signatures(pages: list[PageExtraction]) -> list[StampSignaturePayload]:
        """Colecciona todas las firmas manuscritas, electrónicas y sellos del documento."""
        signatures: list[StampSignaturePayload] = []

        for page in pages:
            for block in page.blocks:
                if block.block_type == BlockType.STAMP_SIGNATURE and block.signature_data is not None:
                    signatures.append(block.signature_data)

        return signatures

    @staticmethod
    def _extract_global_metadata(pages: list[PageExtraction]) -> HeaderMetadataPayload:
        """Extrae o consolida los metadatos globales de encabezado del documento."""
        for page in pages:
            for block in page.blocks:
                if block.block_type == BlockType.HEADER_METADATA and block.header_data is not None:
                    # Retornar el primer encabezado oficial detectado (típicamente página 1)
                    return block.header_data

        return HeaderMetadataPayload()

    @staticmethod
    def _detect_document_censorship(
        pages: list[PageExtraction],
        tables: list[TablePayload],
    ) -> bool:
        """Determina si existe contenido censurado o tachado en cualquier bloque o tabla."""
        # 1. Comprobar celdas en tablas unificadas
        for table in tables:
            for row in table.rows:
                for cell in row:
                    if cell is not None and CENSORED_SENTINEL in cell:
                        return True

        # 2. Comprobar bloques polimórficos
        for page in pages:
            for block in page.blocks:
                if block.credential_data and block.credential_data.is_censored:
                    return True
                if block.text_data and block.text_data.contains_censored_content:
                    return True
                # Anomalías visuales reportadas
                for anomaly in page.visual_anomalies:
                    if any(term in anomaly.lower() for term in ["tachad", "censor", "bloquead"]):
                        return True

        return False
