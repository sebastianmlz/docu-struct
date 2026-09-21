"""Deterministic postprocessing and tabular reconciliation engine.

Reconstructs split tables (vertical & horizontal continuations), aggregates polymorphic
blocks (credentials, signatures, metadata), and evaluates document-wide censorship.
"""

import copy
import logging
import re
import unicodedata

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


def _normalize_header_token(text: str | None) -> str:
    """Normaliza un encabezado para comparación insensible a mayúsculas, espacios y acentos."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    clean = "".join([c for c in nfkd if not unicodedata.combining(c)])
    clean = re.sub(r"[^\w\s]", "", clean.lower()).strip()
    return re.sub(r"\s+", " ", clean)


def _is_generic_header(header: str | None) -> bool:
    """Detecta si un encabezado es genérico o inferido (e.g. 'col_1', 'columna 2', 'campo 3', '')."""
    norm = _normalize_header_token(header)
    if not norm:
        return True
    return bool(re.match(r"^(col|columna|column|campo|field|c)?_?\d+$", norm))


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

    @classmethod
    def _can_stitch_vertical(
        cls, parent: TablePayload, child: TablePayload
    ) -> tuple[bool, str]:
        """Evalúa deterministamente si la tabla hija puede ser una continuación vertical legítima del padre."""
        parent_cols = len(parent.headers)
        child_cols = len(child.headers)
        child_row_cols = len(child.rows[0]) if child.rows else child_cols

        parent_norm = [_normalize_header_token(h) for h in parent.headers]
        child_norm = [_normalize_header_token(h) for h in child.headers]

        child_has_no_real_headers = not child.headers or all(
            _is_generic_header(h) for h in child.headers
        )

        # Caso 1: La tabla hija tiene encabezados explícitos sustanciales
        if not child_has_no_real_headers:
            # A. Identidad exacta o normalizada
            if parent_norm == child_norm:
                return True, "Encabezados idénticos en ambas tablas"

            # B. Misma cantidad de columnas y coincidencia léxica alta (>= 50%)
            if parent_cols > 0 and parent_cols == child_cols:
                matching_count = sum(
                    1
                    for p, c in zip(parent_norm, child_norm, strict=True)
                    if p and c and (p == c or p in c or c in p)
                )
                if (matching_count / parent_cols) >= 0.5:
                    return True, f"Encabezados coincidentes ({matching_count}/{parent_cols} columnas)"

            # C. Encabezados por conjunto de tokens (orden ligeramente alterado pero mismos conceptos)
            parent_set = {t for t in parent_norm if t and not _is_generic_header(t)}
            child_set = {t for t in child_norm if t and not _is_generic_header(t)}
            if parent_set and child_set:
                overlap = parent_set.intersection(child_set)
                overlap_ratio = len(overlap) / max(len(parent_set), len(child_set))
                if overlap_ratio >= 0.6:
                    return True, f"Conjunto de encabezados coincidente (ratio: {overlap_ratio:.2f})"

            # Si tiene encabezados reales pero son sustancialmente disonantes (e.g. ID, PRODUCTO vs PRECIO, STOCK)
            return (
                False,
                f"Encabezados disonantes incompatibles con continuación vertical: "
                f"padre={parent.headers} vs hijo={child.headers}",
            )

        # Caso 2: La tabla hija NO tiene encabezados reales (arranca directamente con filas de datos)
        if child.rows:
            if child_row_cols == parent_cols and (
                parent.split_metadata.has_subsequent_continuation
                or child.split_metadata.is_continuation
            ):
                return (
                    True,
                    f"Continuación sin encabezados repetidos (misma cantidad de columnas: {parent_cols})",
                )
            return (
                False,
                f"Cantidad de columnas en filas ({child_row_cols}) no coincide con tabla matriz ({parent_cols})",
            )

        # Caso de borde: hijo vacío sin filas ni encabezados
        return False, "Tabla hija sin filas ni encabezados válidos para continuación"

    @classmethod
    def _can_stitch_horizontal(
        cls, parent: TablePayload, child: TablePayload
    ) -> tuple[bool, str]:
        """Evalúa si la tabla hija corresponde a columnas adicionales (tabla ancha dividida horizontalmente)."""
        if child.split_metadata.split_type != TableSplitType.HORIZONTAL_CONTINUATION:
            return (
                False,
                f"split_type no es horizontal_continuation (es '{child.split_metadata.split_type}')",
            )

        # Si ambas tienen filas, la cantidad debe ser compatible (permitiendo ligera variación por subtotales)
        if parent.rows and child.rows:
            diff = abs(len(parent.rows) - len(child.rows))
            if diff <= 1 or len(child.rows) <= len(parent.rows):
                return (
                    True,
                    f"Filas compatibles para fusión horizontal (padre: {len(parent.rows)}, hijo: {len(child.rows)})",
                )
            return (
                False,
                f"Discrepancia excesiva de filas para división horizontal ({len(parent.rows)} vs {len(child.rows)})",
            )

        return True, "Estructura válida para fusión horizontal"

    def _reconcile_tables(self, pages: list[PageExtraction]) -> list[TablePayload]:
        """Reconstruye tablas partidas vertical u horizontalmente a lo largo de las páginas."""
        consolidated: list[TablePayload] = []
        table_map: dict[str, TablePayload] = {}
        table_page_map: dict[str, int] = {}
        last_table_seen: TablePayload | None = None
        last_table_page: int | None = None

        # Mapeos locales por página: (page_number, raw_table_id) -> canonical_id
        # Resuelve continuation_of_id en el ámbito local de la página correspondiente
        page_local_to_canonical: dict[int, dict[str, str]] = {}

        # Ordenar páginas por número para procesar secuencialmente
        sorted_pages = sorted(pages, key=lambda p: p.page_number)

        for page in sorted_pages:
            p_num = page.page_number
            page_local_to_canonical[p_num] = {}

            table_blocks = [
                b for b in sorted(page.blocks, key=lambda b: b.reading_order_index)
                if b.block_type == BlockType.TABLE and b.table_data is not None
            ]

            for block_idx, block in enumerate(table_blocks, start=1):
                current_table = copy.deepcopy(block.table_data)
                meta = current_table.split_metadata
                raw_table_id = meta.table_id

                target_parent: TablePayload | None = None

                # Candidato 1: La tabla indica explícitamente ser continuación
                if meta.is_continuation and meta.continuation_of_id:
                    cid = meta.continuation_of_id

                    # 1a. Buscar primero en la MISMA página (e.g. división horizontal intra-página)
                    if cid in page_local_to_canonical[p_num]:
                        canon_id = page_local_to_canonical[p_num][cid]
                        target_parent = table_map.get(canon_id)

                    # 1b. Si no está en la misma página, buscar en la página inmediatamente anterior (P-1)
                    if (
                        target_parent is None
                        and (p_num - 1) in page_local_to_canonical
                        and cid in page_local_to_canonical[p_num - 1]
                    ):
                        canon_id = page_local_to_canonical[p_num - 1][cid]
                        target_parent = table_map.get(canon_id)

                    # 1c. Búsqueda global en table_map sólo si el candidato está a distancia válida
                    if target_parent is None:
                        candidate = table_map.get(cid)
                        if candidate is not None:
                            parent_page = table_page_map.get(cid, p_num)
                            page_diff = abs(p_num - parent_page)
                            # Sólo permitir candidatos en la misma página o contigua (diff <= 1)
                            if page_diff <= 1:
                                target_parent = candidate

                # Candidato 2: Heurística de Resiliencia si continuation_of_id no coincidió o faltó
                if (
                    target_parent is None
                    and last_table_seen is not None
                    and (meta.is_continuation or last_table_seen.split_metadata.has_subsequent_continuation)
                ):
                    page_diff = p_num - (last_table_page or p_num)
                    if page_diff <= 1:
                        can_v_pre, _ = self._can_stitch_vertical(last_table_seen, current_table)
                        can_h_pre, _ = self._can_stitch_horizontal(last_table_seen, current_table)
                        if can_v_pre or can_h_pre:
                            target_parent = last_table_seen
                            logger.info(
                                "Heurística de reconciliación: asociando tabla '%s' como candidata de '%s'",
                                meta.table_id,
                                last_table_seen.split_metadata.table_id,
                            )

                # Si tenemos un padre candidato, validar estrictamente la compatibilidad
                reconciled = False
                if target_parent is not None:
                    parent_id = target_parent.split_metadata.table_id
                    parent_page = table_page_map.get(parent_id, p_num)
                    page_diff = abs(p_num - parent_page)

                    if meta.split_type == TableSplitType.HORIZONTAL_CONTINUATION:
                        if page_diff > 1:
                            logger.warning(
                                "Reconciliación horizontal rechazada entre '%s' (pág %d) y '%s' (pág %d): páginas no consecutivas",
                                meta.table_id,
                                p_num,
                                parent_id,
                                parent_page,
                            )
                        else:
                            can_h, reason_h = self._can_stitch_horizontal(target_parent, current_table)
                            if can_h:
                                self._stitch_horizontal(target_parent, current_table)
                                target_parent.split_metadata.has_subsequent_continuation = (
                                    meta.has_subsequent_continuation
                                )
                                last_table_seen = target_parent
                                last_table_page = p_num
                                reconciled = True
                                page_local_to_canonical[p_num][raw_table_id] = parent_id
                                logger.info(
                                    "Reconciliación horizontal exitosa: tabla '%s' integrada en '%s'",
                                    meta.table_id,
                                    parent_id,
                                )
                            else:
                                logger.warning(
                                    "Reconciliación horizontal rechazada entre '%s' y '%s': %s",
                                    meta.table_id,
                                    parent_id,
                                    reason_h,
                                )
                    else:
                        can_v, reason_v = self._can_stitch_vertical(target_parent, current_table)
                        if can_v:
                            self._stitch_vertical(target_parent, current_table)
                            target_parent.split_metadata.has_subsequent_continuation = (
                                meta.has_subsequent_continuation
                            )
                            last_table_seen = target_parent
                            last_table_page = p_num
                            reconciled = True
                            page_local_to_canonical[p_num][raw_table_id] = parent_id
                            logger.info(
                                "Reconciliación vertical exitosa: tabla '%s' integrada en '%s'",
                                meta.table_id,
                                parent_id,
                            )
                        else:
                            logger.warning(
                                "Reconciliación vertical rechazada entre '%s' y '%s': %s. Se tratará como tabla independiente.",
                                meta.table_id,
                                parent_id,
                                reason_v,
                            )

                if not reconciled:
                    # Es una tabla nueva e independiente
                    meta.is_continuation = False
                    meta.continuation_of_id = None
                    meta.split_type = TableSplitType.NONE

                    # Resolver colisiones de table_id si el ID ya existe en table_map
                    if meta.table_id in table_map:
                        unique_id = f"{meta.table_id}_p{p_num}_b{block_idx}"
                        counter = 2
                        while unique_id in table_map:
                            unique_id = f"{meta.table_id}_p{p_num}_b{block_idx}_{counter}"
                            counter += 1
                        logger.info(
                            "Resolviendo colisión de table_id: reasignando '%s' a '%s'",
                            meta.table_id,
                            unique_id,
                        )
                        meta.table_id = unique_id

                    consolidated.append(current_table)
                    table_map[meta.table_id] = current_table
                    table_page_map[meta.table_id] = p_num
                    page_local_to_canonical[p_num][raw_table_id] = meta.table_id
                    last_table_seen = current_table
                    last_table_page = p_num

        return consolidated

    @staticmethod
    def _stitch_vertical(parent: TablePayload, child: TablePayload) -> None:
        """Fusiona filas continuadas asegurando alineación de columnas y deduplicando cabeceras accidentales."""
        target_col_count = len(parent.headers)
        parent_norm = [_normalize_header_token(h) for h in parent.headers]

        for idx, row in enumerate(child.rows):
            # Detección defensiva: si el LLM incluyó la fila de encabezados como primera fila de datos
            if idx == 0 and len(row) == len(parent_norm):
                row_norm = [_normalize_header_token(c) for c in row]
                if row_norm == parent_norm and any(row_norm):
                    logger.debug("Omitiendo fila 0 de datos de tabla hija por ser encabezado duplicado idéntico")
                    continue

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
