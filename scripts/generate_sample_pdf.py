"""Script to generate a highly realistic 4-page heterogeneous test PDF.

Incorporates all benchmark edge cases:
1. Split & continuous table across Pages 1 & 2.
2. Polymorphic content on Page 3 (embedded national identity card / cédula).
3. Visual redaction / blacked-out censored data in tables.
4. Second independent table and official stamps/signatures on Page 4.
"""

import os

from PIL import Image, ImageDraw, ImageFont

PAGE_WIDTH = 1240
PAGE_HEIGHT = 1754

# Cargar fuentes TrueType estándar de Windows
FONT_TITLE = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 32)
FONT_SUBTITLE = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 24)
FONT_SECTION = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 20)
FONT_BODY = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
FONT_BODY_BOLD = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 18)
FONT_TABLE_HEAD = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 17)
FONT_TABLE_CELL = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 16)
FONT_FOOTER = ImageFont.truetype("C:/Windows/Fonts/ariali.ttf", 15)
FONT_BADGE = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 14)


def create_blank_page() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Crea una página en blanco con fondo sutilmente apergaminado / papel blanco oficial."""
    img = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), color=(252, 252, 253))
    draw = ImageDraw.Draw(img)
    return img, draw


def draw_page_footer(draw: ImageDraw.ImageDraw, current_page: int, total_pages: int = 4):
    """Dibuja la numeración y nota legal de pie de página."""
    draw.line([(80, PAGE_HEIGHT - 80), (PAGE_WIDTH - 80, PAGE_HEIGHT - 80)], fill=(200, 205, 215), width=1)
    footer_text = f"Expediente EXP-2026-MOP-88421 • Documento Oficial de Adjudicación • Página {current_page} de {total_pages}"
    draw.text((80, PAGE_HEIGHT - 65), footer_text, fill=(120, 130, 145), font=FONT_FOOTER)


def generate_page_1() -> Image.Image:
    """Página 1: Membrete oficial, resolución y Parte 1 de la Tabla de Contratistas (Partida)."""
    img, draw = create_blank_page()

    # Membrete institucional
    draw.rectangle([(80, 70), (88, 140)], fill=(30, 58, 138))  # Barra azul lateral
    draw.text((105, 72), "REPÚBLICA DE CHILE", fill=(30, 41, 59), font=FONT_SUBTITLE)
    draw.text((105, 102), "MINISTERIO DE OBRAS PÚBLICAS", fill=(30, 58, 138), font=FONT_TITLE)
    draw.text((105, 140), "DIVISIÓN NACIONAL DE VIALIDAD E INFRAESTRUCTURA", fill=(100, 116, 139), font=FONT_BADGE)

    draw.text((PAGE_WIDTH - 380, 75), "EXPEDIENTE: EXP-2026-MOP-88421", fill=(71, 85, 105), font=FONT_BODY_BOLD)
    draw.text((PAGE_WIDTH - 380, 105), "FECHA: 15 de Septiembre de 2026", fill=(71, 85, 105), font=FONT_BODY)
    draw.text((PAGE_WIDTH - 380, 135), "FOLIO: RES-EX-009412", fill=(71, 85, 105), font=FONT_BODY)

    draw.line([(80, 180), (PAGE_WIDTH - 80, 180)], fill=(203, 213, 225), width=2)

    # Título del Documento
    draw.text((80, 210), "RESOLUCIÓN EXENTA N° 1042 / 2026", fill=(15, 23, 42), font=FONT_SUBTITLE)
    draw.text((80, 245), "APRUEBA NÓMINA DE ADJUDICACIÓN DE OBRAS VIALES - MACROZONA SUR", fill=(51, 65, 85), font=FONT_BODY_BOLD)

    # Texto Narrativo / Considerandos
    p1 = (
        "VISTOS: Los antecedentes contenidos en las bases de licitación pública N° 2026-88, la ley de compras públicas,\n"
        "el informe técnico de la comisión evaluadora y las facultades delegadas mediante Decreto Supremo N° 45."
    )
    draw.text((80, 290), p1, fill=(51, 65, 85), font=FONT_BODY)

    p2 = (
        "CONSIDERANDO: Que se ha evaluado exhaustivamente la solvencia técnica, económica y de acreditación de personería\n"
        "legal de los oferentes participantes, determinándose la adjudicación prioritaria a las siguientes entidades:"
    )
    draw.text((80, 360), p2, fill=(51, 65, 85), font=FONT_BODY)

    # Subtítulo de Tabla
    draw.text((80, 440), "TABLA 1: NÓMINA GENERAL DE CONTRATISTAS Y ASIGNACIONES (FASE INICIAL)", fill=(30, 58, 138), font=FONT_SECTION)

    # Tabla 1 - Parte 1
    # Columnas: ID Contrato (140px), Razón Social (360px), RUT Proveedor (190px), Monto (220px), Estado (170px)
    start_y = 480
    col_widths = [140, 360, 190, 220, 170]
    headers = ["ID Contrato", "Razón Social", "RUT Proveedor", "Monto Asignado", "Estado"]

    # Header de la tabla
    curr_x = 80
    draw.rectangle([(curr_x, start_y), (curr_x + sum(col_widths), start_y + 45)], fill=(241, 245, 249))
    draw.rectangle([(curr_x, start_y), (curr_x + sum(col_widths), start_y + 45)], outline=(148, 163, 184), width=1)

    for _idx, (h, w) in enumerate(zip(headers, col_widths, strict=True)):
        draw.text((curr_x + 12, start_y + 12), h, fill=(30, 41, 59), font=FONT_TABLE_HEAD)
        draw.line([(curr_x, start_y), (curr_x, start_y + 45)], fill=(203, 213, 225), width=1)
        curr_x += w

    # Filas
    rows = [
        ["CTR-001", "Constructora Austral S.A.", "76.123.456-7", "$ 120.000.000", "Aprobado"],
        ["CTR-002", "Ingeniería y Pavimentos Ltda.", "78.987.654-2", "$ 85.500.000", "Aprobado"],
        ["CTR-003", "Desarrollos Viales del Norte SpA", "96.444.333-1", "[CENSURADO]", "En Revisión"],
        ["CTR-004", "Consorcio Infraestructura Sur", "77.555.666-8", "$ 64.000.000", "Aprobado"],
        ["CTR-005", "Áridos y Hormigones del Maule", "79.222.333-9", "$ 92.400.000", "Aprobado"],
        ["CTR-006", "Servicios de Maquinaria Central", "76.777.888-0", "$ 115.000.000", "Aprobado"],
    ]

    row_y = start_y + 45
    for r_idx, row in enumerate(rows):
        curr_x = 80
        row_bg = (255, 255, 255) if r_idx % 2 == 0 else (248, 250, 252)
        draw.rectangle([(curr_x, row_y), (curr_x + sum(col_widths), row_y + 42)], fill=row_bg, outline=(226, 232, 240), width=1)

        for c_idx, (val, w) in enumerate(zip(row, col_widths, strict=True)):
            # Caso Censura: en la fila 2 (CTR-003), columna monto (índice 3), dibujar una barra negra de marcador
            if r_idx == 2 and c_idx == 3:
                # Dibujar barra negra de censura realista
                draw.rectangle([(curr_x + 10, row_y + 8), (curr_x + w - 15, row_y + 34)], fill=(15, 23, 42))
                # Dibujar texto tenue tapado o centinela
                draw.text((curr_x + 18, row_y + 11), "[DATO CENSURADO]", fill=(148, 163, 184), font=FONT_BADGE)
            else:
                draw.text((curr_x + 12, row_y + 11), val, fill=(51, 65, 85), font=FONT_TABLE_CELL)

            draw.line([(curr_x, row_y), (curr_x, row_y + 42)], fill=(226, 232, 240), width=1)
            curr_x += w

        row_y += 42

    # Línea inferior de la tabla cortada
    draw.line([(80, row_y), (80 + sum(col_widths), row_y)], fill=(148, 163, 184), width=1)

    # Indicador de continuación explícita
    cont_box_y = row_y + 20
    draw.rectangle([(80, cont_box_y), (PAGE_WIDTH - 80, cont_box_y + 50)], fill=(254, 243, 199), outline=(245, 158, 11), width=1)
    draw.text((105, cont_box_y + 14), "⚠️ NOTA DE CONTINUIDAD: La Tabla 1 se divide por límite de espacio de página. Continúa en la Página 2.", fill=(146, 64, 14), font=FONT_BODY_BOLD)

    # Párrafo complementario inferior
    draw.text((80, cont_box_y + 80), "La verificación de boletas de garantía de fiel cumplimiento se formaliza en el anexo de garantías financieras adjunto.", fill=(71, 85, 105), font=FONT_BODY)

    draw_page_footer(draw, 1)
    return img


def generate_page_2() -> Image.Image:
    """Página 2: Continuación estricta de la Tabla 1 y párrafos de cierre resolutivo."""
    img, draw = create_blank_page()

    # Encabezado secundario
    draw.text((80, 80), "EXPEDIENTE EXP-2026-MOP-88421", fill=(100, 116, 139), font=FONT_BADGE)
    draw.text((80, 105), "RESOLUCIÓN EXENTA N° 1042 / 2026 (CONTINUACIÓN)", fill=(30, 41, 59), font=FONT_SUBTITLE)
    draw.line([(80, 145), (PAGE_WIDTH - 80, 145)], fill=(203, 213, 225), width=1)

    # Título de Tabla Continuada
    draw.text((80, 175), "TABLA 1: NÓMINA GENERAL DE CONTRATISTAS (CONTINUACIÓN PÁGINA 2)", fill=(30, 58, 138), font=FONT_SECTION)

    # Misma estructura de columnas para verificar stitching
    start_y = 215
    col_widths = [140, 360, 190, 220, 170]
    headers = ["ID Contrato", "Razón Social", "RUT Proveedor", "Monto Asignado", "Estado"]

    # Header
    curr_x = 80
    draw.rectangle([(curr_x, start_y), (curr_x + sum(col_widths), start_y + 45)], fill=(241, 245, 249))
    draw.rectangle([(curr_x, start_y), (curr_x + sum(col_widths), start_y + 45)], outline=(148, 163, 184), width=1)

    for h, w in zip(headers, col_widths, strict=True):
        draw.text((curr_x + 12, start_y + 12), h, fill=(30, 41, 59), font=FONT_TABLE_HEAD)
        draw.line([(curr_x, start_y), (curr_x, start_y + 45)], fill=(203, 213, 225), width=1)
        curr_x += w

    # Filas continuadas (CTR-007 a CTR-011)
    rows_p2 = [
        ["CTR-007", "Técnicas de Asfaltado Austral", "79.111.222-3", "$ 78.900.000", "Aprobado"],
        ["CTR-008", "Consultores Viales Asociados", "77.888.999-0", "[CENSURADO CON MARCADOR]", "Pendiente"],
        ["CTR-009", "Puentes y Dragados del Sur SpA", "96.222.111-9", "$ 195.000.000", "Aprobado"],
        ["CTR-010", "Señalización y Seguridad Ltda.", "76.444.555-4", "$ 33.200.000", "Aprobado"],
        ["CTR-011", "Mantenciones Viales Patagonia", "78.333.111-6", "$ 88.000.000", "Aprobado"],
    ]

    row_y = start_y + 45
    for r_idx, row in enumerate(rows_p2):
        curr_x = 80
        row_bg = (255, 255, 255) if r_idx % 2 == 0 else (248, 250, 252)
        draw.rectangle([(curr_x, row_y), (curr_x + sum(col_widths), row_y + 42)], fill=row_bg, outline=(226, 232, 240), width=1)

        for c_idx, (val, w) in enumerate(zip(row, col_widths, strict=True)):
            # Caso Censura 2: En fila 1 (CTR-008), columna monto (índice 3), cinta correctora / barra negra
            if r_idx == 1 and c_idx == 3:
                draw.rectangle([(curr_x + 10, row_y + 8), (curr_x + w - 15, row_y + 34)], fill=(15, 23, 42))
                draw.text((curr_x + 20, row_y + 11), "[CENSURADO]", fill=(248, 113, 113), font=FONT_BADGE)
            else:
                draw.text((curr_x + 12, row_y + 11), val, fill=(51, 65, 85), font=FONT_TABLE_CELL)

            draw.line([(curr_x, row_y), (curr_x, row_y + 42)], fill=(226, 232, 240), width=1)
            curr_x += w

        row_y += 42

    # Fila de Cierre y Totales
    draw.rectangle([(80, row_y), (80 + sum(col_widths), row_y + 45)], fill=(226, 232, 240), outline=(148, 163, 184), width=1)
    draw.text((95, row_y + 12), "TOTAL CONSOLIDADO: 11 CONTRATOS ASIGNADOS", fill=(15, 23, 42), font=FONT_BODY_BOLD)
    draw.text((80 + sum(col_widths) - 250, row_y + 12), "$ 872.000.000 (Estimado)", fill=(30, 58, 138), font=FONT_BODY_BOLD)

    # Texto Legal de Aprobación
    text_y = row_y + 80
    draw.text((80, text_y), "DISPOSICIONES FINALES Y CONDICIONES GENERALES:", fill=(15, 23, 42), font=FONT_SECTION)

    p_fin = (
        "1. Los adjudicatarios dispondrán de un plazo de 15 días hábiles a contar de la presente notificación para concurrir a la suscripción\n"
        "   del contrato definitivo ante la Notaría autorizada que se consigna en el Anexo 1.\n\n"
        "2. El monto asignado a las partidas confidenciales sujetas a reserva conforme al artículo 8 de la Ley de Transparencia queda consignado\n"
        "   en acta reservada custodiada por la Subsecretaría de Obras Públicas.\n\n"
        "3. Cualquier discrepancia o reparo administrativo deberá deducirse ante el Tribunal de Contratación Pública en tiempo y forma."
    )
    draw.text((80, text_y + 40), p_fin, fill=(51, 65, 85), font=FONT_BODY)

    draw_page_footer(draw, 2)
    return img


def generate_page_3() -> Image.Image:
    """Página 3: Documento Polimórfico con Cédula de Identidad incrustada visualmente."""
    img, draw = create_blank_page()

    # Cabecera de Anexo
    draw.text((80, 80), "EXPEDIENTE EXP-2026-MOP-88421 • ANEXO DOCUMENTAL 1", fill=(100, 116, 139), font=FONT_BADGE)
    draw.text((80, 105), "ACREDITACIÓN DE IDENTIDAD Y PERSONERÍA LEGAL", fill=(30, 41, 59), font=FONT_SUBTITLE)
    draw.line([(80, 145), (PAGE_WIDTH - 80, 145)], fill=(203, 213, 225), width=1)

    p_intro = (
        "En cumplimiento de los requisitos de comparecencia y firma digital, se adjunta copia digitalizada de la Cédula Nacional\n"
        "de Identidad del Representante Legal titular de la entidad con mayor adjudicación presupuestaria:"
    )
    draw.text((80, 175), p_intro, fill=(51, 65, 85), font=FONT_BODY)

    # =========================================================================
    # CÉDULA DE IDENTIDAD CHILENA DIBUJADA (Carnet plastificado realista)
    # =========================================================================
    card_x = 220
    card_y = 260
    card_w = 800
    card_h = 480

    # Sombra del carnet
    draw.rounded_rectangle([(card_x + 8, card_y + 8), (card_x + card_w + 8, card_y + card_h + 8)], radius=24, fill=(203, 213, 225))
    # Cuerpo del carnet (fondo azul cielo y blanco degradado simulado)
    draw.rounded_rectangle([(card_x, card_y), (card_x + card_w, card_y + card_h)], radius=24, fill=(240, 249, 255), outline=(56, 189, 248), width=3)

    # Encabezado del Carnet
    draw.text((card_x + 40, card_y + 30), "REPÚBLICA DE CHILE", fill=(3, 105, 161), font=FONT_BADGE)
    draw.text((card_x + 40, card_y + 50), "SERVICIO DE REGISTRO CIVIL E IDENTIFICACIÓN", fill=(12, 74, 110), font=FONT_BODY_BOLD)
    draw.text((card_x + card_w - 280, card_y + 35), "CÉDULA DE IDENTIDAD", fill=(14, 116, 144), font=FONT_SUBTITLE)

    # Cuadro de Fotografía simulada
    draw.rounded_rectangle([(card_x + 40, card_y + 100), (card_x + 220, card_y + 350)], radius=12, fill=(224, 231, 255), outline=(147, 197, 253), width=2)
    # Silueta de avatar
    draw.ellipse([(card_x + 95, card_y + 140), (card_x + 165, card_y + 210)], fill=(99, 102, 241))
    draw.chord([(card_x + 65, card_y + 230), (card_x + 195, card_y + 340)], start=0, end=180, fill=(99, 102, 241))
    draw.text((card_x + 95, card_y + 310), "FOTO OFICIAL", fill=(100, 116, 139), font=FONT_BADGE)

    # Datos Personales en el Carnet
    info_x = card_x + 250
    draw.text((info_x, card_y + 110), "APELLIDOS / SURNAME:", fill=(100, 116, 139), font=FONT_BADGE)
    draw.text((info_x, card_y + 130), "GONZÁLEZ PÉREZ", fill=(15, 23, 42), font=FONT_SUBTITLE)

    draw.text((info_x, card_y + 170), "NOMBRES / GIVEN NAMES:", fill=(100, 116, 139), font=FONT_BADGE)
    draw.text((info_x, card_y + 190), "SEBASTIÁN ANDRÉS", fill=(15, 23, 42), font=FONT_SUBTITLE)

    draw.text((info_x, card_y + 230), "NACIONALIDAD:", fill=(100, 116, 139), font=FONT_BADGE)
    draw.text((info_x, card_y + 250), "CHILENA", fill=(15, 23, 42), font=FONT_BODY_BOLD)

    draw.text((info_x + 260, card_y + 230), "FECHA DE NACIMIENTO:", fill=(100, 116, 139), font=FONT_BADGE)
    draw.text((info_x + 260, card_y + 250), "14 MAY 1992", fill=(15, 23, 42), font=FONT_BODY_BOLD)

    draw.text((info_x, card_y + 290), "FECHA DE EMISIÓN:", fill=(100, 116, 139), font=FONT_BADGE)
    draw.text((info_x, card_y + 310), "20 ENE 2022", fill=(15, 23, 42), font=FONT_BODY)

    draw.text((info_x + 260, card_y + 290), "FECHA DE VENCIMIENTO:", fill=(100, 116, 139), font=FONT_BADGE)
    draw.text((info_x + 260, card_y + 310), "14 MAY 2032", fill=(15, 23, 42), font=FONT_BODY_BOLD)

    # RUN destacado en el borde inferior
    draw.rectangle([(card_x + 40, card_y + 380), (card_x + card_w - 40, card_y + 440)], fill=(15, 23, 42))
    draw.text((card_x + 60, card_y + 395), "NÚMERO IDENTIFICADOR (RUN):", fill=(148, 163, 184), font=FONT_BODY)
    draw.text((card_x + 360, card_y + 392), "18.999.888-K", fill=(255, 255, 255), font=FONT_SUBTITLE)

    # =========================================================================
    # Texto Legal Posterior
    # =========================================================================
    post_text_y = card_y + card_h + 60
    draw.text((80, post_text_y), "CERTIFICACIÓN NOTARIAL DE VIGENCIA DE PERSONERÍA:", fill=(15, 23, 42), font=FONT_SECTION)

    p_cert = (
        "Certifico que don Sebastián Andrés González Pérez, cédula de identidad N° 18.999.888-K, actúa en representación legal\n"
        "de Constructora Austral S.A., con facultades plenamente vigentes según constan en la escritura pública de fecha 10 de Agosto\n"
        "de 2025, otorgada en el repertorio notarial N° 45.891-2025, facultado expresamente para la celebración de contratos de obra\n"
        "pública y recepción de estados de pago fiscales."
    )
    draw.text((80, post_text_y + 35), p_cert, fill=(51, 65, 85), font=FONT_BODY)

    draw_page_footer(draw, 3)
    return img


def generate_page_4() -> Image.Image:
    """Página 4: Tabla 2 (Evaluación Técnica Independiente) y Sellos / Firmas Institucionales."""
    img, draw = create_blank_page()

    # Encabezado
    draw.text((80, 80), "EXPEDIENTE EXP-2026-MOP-88421 • ANEXO 2", fill=(100, 116, 139), font=FONT_BADGE)
    draw.text((80, 105), "MATRIZ DE EVALUACIÓN TÉCNICA FINAL Y CIERRE NOTARIAL", fill=(30, 41, 59), font=FONT_SUBTITLE)
    draw.line([(80, 145), (PAGE_WIDTH - 80, 145)], fill=(203, 213, 225), width=1)

    p_desc = (
        "A continuación se presenta el consolidado de puntuaciones técnicas y económicas ponderadas por la comisión de expertos,\n"
        "determinando la adjudicación definitiva:"
    )
    draw.text((80, 175), p_desc, fill=(51, 65, 85), font=FONT_BODY)

    # =========================================================================
    # TABLA 2: Matriz de Evaluación (Independiente)
    # =========================================================================
    draw.text((80, 240), "TABLA 2: PONDERACIÓN TÉCNICA, ECONÓMICA Y CALIFICACIÓN", fill=(30, 58, 138), font=FONT_SECTION)

    start_y = 280
    col_widths = [320, 190, 190, 200, 180]
    headers = ["Entidad Oferente", "Puntaje Técnico", "Puntaje Económico", "Puntaje Total", "Resolución"]

    curr_x = 80
    draw.rectangle([(curr_x, start_y), (curr_x + sum(col_widths), start_y + 45)], fill=(241, 245, 249))
    draw.rectangle([(curr_x, start_y), (curr_x + sum(col_widths), start_y + 45)], outline=(148, 163, 184), width=1)

    for h, w in zip(headers, col_widths, strict=True):
        draw.text((curr_x + 12, start_y + 12), h, fill=(30, 41, 59), font=FONT_TABLE_HEAD)
        draw.line([(curr_x, start_y), (curr_x, start_y + 45)], fill=(203, 213, 225), width=1)
        curr_x += w

    # Filas con censura visual en fila 3
    t2_rows = [
        ["Constructora Austral S.A.", "48.5 / 50", "47.0 / 50", "95.5 / 100", "Adjudicado"],
        ["Ingeniería y Pavimentos Ltda.", "45.0 / 50", "42.5 / 50", "87.5 / 100", "Lista Espera"],
        ["Consorcio Infraestructura Sur", "[DATO CENSURADO]", "38.0 / 50", "[CENSURADO]", "Descalificado"],
        ["Técnicas de Asfaltado Austral", "42.0 / 50", "41.0 / 50", "83.0 / 100", "Adjudicado"],
    ]

    row_y = start_y + 45
    for r_idx, row in enumerate(t2_rows):
        curr_x = 80
        row_bg = (255, 255, 255) if r_idx % 2 == 0 else (248, 250, 252)
        draw.rectangle([(curr_x, row_y), (curr_x + sum(col_widths), row_y + 42)], fill=row_bg, outline=(226, 232, 240), width=1)

        for c_idx, (val, w) in enumerate(zip(row, col_widths, strict=True)):
            # Censura en fila 2, columnas 1 y 3
            if r_idx == 2 and (c_idx == 1 or c_idx == 3):
                draw.rectangle([(curr_x + 8, row_y + 8), (curr_x + w - 12, row_y + 34)], fill=(15, 23, 42))
                draw.text((curr_x + 15, row_y + 11), "[CENSURADO]", fill=(248, 113, 113), font=FONT_BADGE)
            else:
                draw.text((curr_x + 12, row_y + 11), val, fill=(51, 65, 85), font=FONT_TABLE_CELL)

            draw.line([(curr_x, row_y), (curr_x, row_y + 42)], fill=(226, 232, 240), width=1)
            curr_x += w

        row_y += 42

    draw.line([(80, row_y), (80 + sum(col_widths), row_y)], fill=(148, 163, 184), width=1)

    # =========================================================================
    # BLOQUE DE AUTENTICACIÓN (Sellos y Firmas)
    # =========================================================================
    auth_y = row_y + 90
    draw.line([(80, auth_y - 20), (PAGE_WIDTH - 80, auth_y - 20)], fill=(203, 213, 225), width=2)
    draw.text((80, auth_y), "CONSTANCIA NOTARIAL Y SUSCRIPCIÓN DE AUTORIDADES COMPETENTES:", fill=(15, 23, 42), font=FONT_SECTION)

    p_sign = "En fe de lo actuado y para los efectos legales consiguientes, firman y timbran en Santiago a 15 de Septiembre de 2026."
    draw.text((80, auth_y + 35), p_sign, fill=(71, 85, 105), font=FONT_BODY)

    # --- FIRMA 1: Director de Obras Públicas ---
    f1_x = 120
    f1_y = auth_y + 160
    # Trazo manuscrito simulado
    draw.line([(f1_x, f1_y + 20), (f1_x + 40, f1_y - 15), (f1_x + 80, f1_y + 25), (f1_x + 140, f1_y - 10), (f1_x + 220, f1_y + 15), (f1_x + 300, f1_y + 5)], fill=(30, 58, 138), width=3)
    draw.line([(f1_x, f1_y + 30), (f1_x + 320, f1_y + 30)], fill=(71, 85, 105), width=1)
    draw.text((f1_x + 10, f1_y + 40), "ING. ROBERTO CARRASCO MORALES", fill=(15, 23, 42), font=FONT_BODY_BOLD)
    draw.text((f1_x + 35, f1_y + 65), "Director General de Obras Públicas", fill=(71, 85, 105), font=FONT_BODY)
    draw.text((f1_x + 50, f1_y + 90), "Ministerio de Obras Públicas", fill=(100, 116, 139), font=FONT_BADGE)

    # --- SELLO INSTITUCIONAL CIRCULAR (Estilo timbre de goma) ---
    stamp_center_x = 580
    stamp_center_y = f1_y + 35
    stamp_radius = 80
    draw.ellipse([(stamp_center_x - stamp_radius, stamp_center_y - stamp_radius), (stamp_center_x + stamp_radius, stamp_center_y + stamp_radius)], outline=(185, 28, 28), width=3)
    draw.ellipse([(stamp_center_x - stamp_radius + 6, stamp_center_y - stamp_radius + 6), (stamp_center_x + stamp_radius - 6, stamp_center_y + stamp_radius - 6)], outline=(185, 28, 28), width=1)
    draw.text((stamp_center_x - 55, stamp_center_y - 45), "REPÚBLICA DE CHILE", fill=(185, 28, 28), font=FONT_BADGE)
    draw.text((stamp_center_x - 50, stamp_center_y - 15), "★ M.O.P. ★", fill=(185, 28, 28), font=FONT_SECTION)
    draw.text((stamp_center_x - 65, stamp_center_y + 15), "DIVISIÓN CONTRATOS", fill=(185, 28, 28), font=FONT_BADGE)
    draw.text((stamp_center_x - 55, stamp_center_y + 35), "15 SEP 2026 - TOMA RAZÓN", fill=(185, 28, 28), font=FONT_BADGE)

    # --- FIRMA 2: Notario Público / Ministro de Fe ---
    f2_x = 760
    f2_y = f1_y
    draw.line([(f2_x, f2_y + 10), (f2_x + 50, f2_y - 20), (f2_x + 100, f2_y + 20), (f2_x + 180, f2_y - 5), (f2_x + 280, f2_y + 10)], fill=(15, 23, 42), width=3)
    draw.line([(f2_x, f2_y + 30), (f2_x + 320, f2_y + 30)], fill=(71, 85, 105), width=1)
    draw.text((f2_x + 40, f2_y + 40), "CARLOS VALENZUELA M.", fill=(15, 23, 42), font=FONT_BODY_BOLD)
    draw.text((f2_x + 35, f2_y + 65), "Notario Público y Ministro de Fe", fill=(71, 85, 105), font=FONT_BODY)
    draw.text((f2_x + 50, f2_y + 90), "24° Notaría de Santiago - Chile", fill=(100, 116, 139), font=FONT_BADGE)

    draw_page_footer(draw, 4)
    return img


def main():
    print("Generando páginas de prueba visual...")
    p1 = generate_page_1()
    p2 = generate_page_2()
    p3 = generate_page_3()
    p4 = generate_page_4()

    output_path = "documento_prueba_heterogeneo.pdf"
    print(f"Guardando PDF multi-página en '{output_path}'...")
    p1.save(
        output_path,
        save_all=True,
        append_images=[p2, p3, p4],
        resolution=150.0,
    )
    file_size_kb = os.path.getsize(output_path) / 1024
    print(f"¡PDF generado con éxito! Archivo: '{output_path}' ({file_size_kb:.1f} KB, 4 páginas)")


if __name__ == "__main__":
    main()
