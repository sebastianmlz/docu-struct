/**
 * DocuStruct - Enterprise Frontend Client Logic
 * Native JavaScript (ES6+), Zero External Frameworks, Zero Emojis, Strict XSS Defense.
 */

document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("fileInput");
    const selectedFileCard = document.getElementById("selectedFileCard");
    const selectedFileName = document.getElementById("selectedFileName");
    const selectedFileSize = document.getElementById("selectedFileSize");
    const btnRemoveFile = document.getElementById("btnRemoveFile");
    const btnProcess = document.getElementById("btnProcess");

    const processingState = document.getElementById("processingState");
    const elapsedTimeCounter = document.getElementById("elapsedTimeCounter");
    const errorAlert = document.getElementById("errorAlert");
    const errorAlertTitle = document.getElementById("errorAlertTitle");
    const errorAlertMessage = document.getElementById("errorAlertMessage");

    const resultsSection = document.getElementById("resultsSection");
    const resultDocTitle = document.getElementById("resultDocTitle");
    const resultDocMeta = document.getElementById("resultDocMeta");
    const metricPages = document.getElementById("metricPages");
    const metricDuration = document.getElementById("metricDuration");
    const metricTables = document.getElementById("metricTables");
    const metricCensorshipBadge = document.getElementById("metricCensorshipBadge");

    const countTables = document.getElementById("countTables");
    const countCredentials = document.getElementById("countCredentials");
    const countSignatures = document.getElementById("countSignatures");

    const tablesContainer = document.getElementById("tablesContainer");
    const credentialsContainer = document.getElementById("credentialsContainer");
    const globalMetadataContent = document.getElementById("globalMetadataContent");
    const signaturesContainer = document.getElementById("signaturesContainer");
    const pagesContainer = document.getElementById("pagesContainer");
    const jsonOutput = document.getElementById("jsonOutput");
    const btnCopyJson = document.getElementById("btnCopyJson");
    const copyBtnText = document.getElementById("copyBtnText");

    let currentFile = null;
    let timerInterval = null;
    let lastResultPayload = null;

    // =================================================================
    // Drag and Drop & File Handling
    // =================================================================

    dropzone.addEventListener("click", () => fileInput.click());

    ["dragenter", "dragover"].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add("border-zinc-500", "bg-zinc-900/80");
        });
    });

    ["dragleave", "drop"].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove("border-zinc-500", "bg-zinc-900/80");
        });
    });

    dropzone.addEventListener("drop", (e) => {
        const files = e.dataTransfer.files;
        if (files && files.length > 0) {
            handleFileSelection(files[0]);
        }
    });

    fileInput.addEventListener("change", () => {
        if (fileInput.files && fileInput.files.length > 0) {
            handleFileSelection(fileInput.files[0]);
        }
    });

    btnRemoveFile.addEventListener("click", () => {
        currentFile = null;
        fileInput.value = "";
        selectedFileCard.classList.add("hidden");
        dropzone.classList.remove("hidden");
        hideError();
    });

    function handleFileSelection(file) {
        if (!file.name.toLowerCase().endsWith(".pdf")) {
            showError("Formato Incompatible", "Selecciona exclusivamente un archivo con extensión .pdf.");
            return;
        }

        currentFile = file;
        selectedFileName.textContent = file.name;
        selectedFileSize.textContent = `${(file.size / (1024 * 1024)).toFixed(2)} MB`;

        hideError();
        dropzone.classList.add("hidden");
        selectedFileCard.classList.remove("hidden");
    }

    // =================================================================
    // Processing and Fetch API
    // =================================================================

    btnProcess.addEventListener("click", async () => {
        if (!currentFile) return;

        hideError();
        resultsSection.classList.add("hidden");
        processingState.classList.remove("hidden");
        btnProcess.disabled = true;

        const startTime = Date.now();
        elapsedTimeCounter.textContent = "0.0s";
        timerInterval = setInterval(() => {
            const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
            elapsedTimeCounter.textContent = `${elapsed}s`;
        }, 100);

        const formData = new FormData();
        formData.append("file", currentFile);

        try {
            const response = await fetch("/api/v1/documents/process", {
                method: "POST",
                body: formData,
            });

            clearInterval(timerInterval);
            processingState.classList.add("hidden");
            btnProcess.disabled = false;

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                const message = errData.detail || `Error del servidor HTTP ${response.status}`;
                showError("Fallo en Análisis Forense", message);
                return;
            }

            const result = await response.json();
            lastResultPayload = result;
            renderResults(result);

        } catch (err) {
            clearInterval(timerInterval);
            processingState.classList.add("hidden");
            btnProcess.disabled = false;
            showError("Error de Conectividad", "No se pudo establecer comunicación con el microservicio DocuStruct.");
            console.error(err);
        }
    });

    // =================================================================
    // Rendering Engine (Clean Forensic Layout, Zero Emojis)
    // =================================================================

    function renderResults(res) {
        const data = res.data;
        const metrics = res.metrics;

        // Metadatos y Cabecera de Resultados
        resultDocTitle.textContent = data.filename;
        resultDocMeta.textContent = `ID: ${data.document_id} &bull; Registro: ${metrics.timestamp.slice(0, 19)}`;

        metricPages.textContent = metrics.total_pages_processed;
        metricDuration.textContent = `${metrics.duration_seconds}s`;
        metricTables.textContent = data.unified_tables.length;

        // Badge de Censura Global con SVG Vectorial
        if (data.has_censored_content) {
            metricCensorshipBadge.className = "px-2.5 py-1 rounded font-medium border bg-amber-950/40 text-amber-300 border-amber-800/60 flex items-center gap-1.5";
            metricCensorshipBadge.innerHTML = `
                <svg class="w-3.5 h-3.5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.008v.008H12v-.008z"/>
                </svg>
                <span>Censura Detectada</span>
            `;
        } else {
            metricCensorshipBadge.className = "px-2.5 py-1 rounded font-medium border bg-emerald-950/40 text-emerald-300 border-emerald-800/60 flex items-center gap-1.5";
            metricCensorshipBadge.innerHTML = `
                <svg class="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5"/>
                </svg>
                <span>Sin Censura</span>
            `;
        }

        // Contadores de Tabs
        countTables.textContent = data.unified_tables.length;
        countCredentials.textContent = data.extracted_credentials.length;
        countSignatures.textContent = data.extracted_signatures.length;

        // 1. Render Tablas Reconciliadas
        renderTables(data.unified_tables);

        // 2. Render Credenciales
        renderCredentials(data.extracted_credentials);

        // 3. Render Firmas y Metadatos
        renderSignaturesAndMetadata(data.global_metadata, data.extracted_signatures);

        // 4. Render Páginas Secuenciales
        renderPages(data.pages);

        // 5. Render JSON Crudo
        jsonOutput.textContent = JSON.stringify(res, null, 2);

        // Mostrar sección de resultados
        resultsSection.classList.remove("hidden");
        resultsSection.scrollIntoView({ behavior: "smooth" });
    }

    function renderTables(tables) {
        tablesContainer.innerHTML = "";

        if (!tables || tables.length === 0) {
            tablesContainer.innerHTML = `
                <div class="p-8 text-center rounded-lg bg-zinc-900/30 border border-zinc-800 text-zinc-500 text-xs font-mono">
                    No se detectaron estructuras tabulares en el documento.
                </div>
            `;
            return;
        }

        tables.forEach((tbl, idx) => {
            const tableCard = document.createElement("div");
            tableCard.className = "bg-zinc-900/50 border border-zinc-800 rounded-lg overflow-hidden shadow-sm";

            const meta = tbl.split_metadata || {};
            let splitBadge = "";
            if (meta.is_continuation) {
                splitBadge = `<span class="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700 font-mono text-[10px]">Reconciliada (${meta.split_type || "Continuación"})</span>`;
            }

            const headerHtml = `
                <div class="px-4 py-3 bg-zinc-950/80 border-b border-zinc-800 flex items-center justify-between flex-wrap gap-2">
                    <div class="flex items-center gap-2">
                        <span class="text-[11px] font-mono font-semibold text-zinc-400 bg-zinc-800/80 px-2 py-0.5 rounded">Tabla #${idx + 1}</span>
                        <h4 class="text-xs font-semibold text-zinc-100 font-mono">${escapeHtml(tbl.caption || meta.table_id || "Estructura Tabular")}</h4>
                    </div>
                    <div class="flex items-center gap-2">
                        ${splitBadge}
                        <span class="text-xs font-mono text-zinc-400">${tbl.rows ? tbl.rows.length : 0} filas &bull; ${tbl.headers ? tbl.headers.length : 0} cols</span>
                    </div>
                </div>
            `;

            let tableHtml = `<div class="overflow-x-auto custom-scrollbar"><table class="w-full text-left text-xs text-zinc-300">`;
            
            // Encabezados
            if (tbl.headers && tbl.headers.length > 0) {
                tableHtml += `<thead class="bg-zinc-950 text-zinc-400 font-mono text-[11px] border-b border-zinc-800"><tr>`;
                tbl.headers.forEach(h => {
                    tableHtml += `<th class="px-3.5 py-2.5 whitespace-nowrap">${escapeHtml(h)}</th>`;
                });
                tableHtml += `</tr></thead>`;
            }

            // Filas
            tableHtml += `<tbody class="divide-y divide-zinc-800/60 font-mono text-xs">`;
            if (tbl.rows && tbl.rows.length > 0) {
                tbl.rows.forEach(row => {
                    tableHtml += `<tr class="hover:bg-zinc-800/30 transition">`;
                    row.forEach(cell => {
                        let cellContent = "";
                        if (cell === null || cell === undefined) {
                            cellContent = `<span class="text-zinc-600 italic">null</span>`;
                        } else if (cell.includes("[DATO_CENSURADO]")) {
                            cellContent = `<span class="px-2 py-0.5 rounded bg-red-950/70 text-red-300 border border-red-800/80 font-mono font-bold text-[10px] inline-block tracking-tight">[DATO_CENSURADO]</span>`;
                        } else {
                            cellContent = escapeHtml(String(cell));
                        }
                        tableHtml += `<td class="px-3.5 py-2 whitespace-nowrap">${cellContent}</td>`;
                    });
                    tableHtml += `</tr>`;
                });
            } else {
                tableHtml += `<tr><td colspan="${tbl.headers.length}" class="px-4 py-3 text-center text-zinc-600">Sin filas registradas</td></tr>`;
            }
            tableHtml += `</tbody></table></div>`;

            tableCard.innerHTML = headerHtml + tableHtml;
            tablesContainer.appendChild(tableCard);
        });
    }

    function renderCredentials(creds) {
        credentialsContainer.innerHTML = "";

        if (!creds || creds.length === 0) {
            credentialsContainer.innerHTML = `
                <div class="col-span-full p-8 text-center rounded-lg bg-zinc-900/30 border border-zinc-800 text-zinc-500 text-xs font-mono">
                    No se detectaron cédulas de identidad ni carnets en el documento.
                </div>
            `;
            return;
        }

        creds.forEach(c => {
            const card = document.createElement("div");
            card.className = "bg-zinc-900/50 border border-zinc-800 rounded-lg p-4 space-y-3 relative overflow-hidden shadow-sm";

            const censoredBanner = c.is_censored
                ? `<span class="absolute top-3 right-3 px-2 py-0.5 rounded bg-red-950/60 text-red-300 border border-red-800/70 text-[10px] font-mono uppercase font-bold">Censurado</span>`
                : "";

            card.innerHTML = `
                ${censoredBanner}
                <div class="flex items-center gap-3">
                    <div class="w-8 h-8 rounded bg-zinc-800 border border-zinc-700 flex items-center justify-center text-zinc-300 shrink-0">
                        <!-- ID Card SVG Icon (No Emojis) -->
                        <svg class="w-4 h-4 text-zinc-300" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.75">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M15 9h3.75M15 12h3.75M15 15h3.75M4.5 19.5h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5zm6-10.125a1.875 1.875 0 11-3.75 0 1.875 1.875 0 013.75 0zm1.294 6.336a6.721 6.721 0 01-3.17.789 6.721 6.721 0 01-3.168-.789 3.376 3.376 0 016.338 0z"/>
                        </svg>
                    </div>
                    <div>
                        <span class="text-[10px] font-mono uppercase text-zinc-400 font-semibold">${escapeHtml(c.credential_type || "Credencial")}</span>
                        <h4 class="text-xs font-semibold text-zinc-100 font-mono">${escapeHtml(c.full_name || "Nombre no consignado")}</h4>
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-2 text-xs pt-2.5 border-t border-zinc-800/80 font-mono">
                    <div>
                        <span class="text-zinc-500 block text-[10px]">Identificador:</span>
                        <strong class="text-zinc-200">${escapeHtml(c.id_number || "N/A")}</strong>
                    </div>
                    <div>
                        <span class="text-zinc-500 block text-[10px]">Nacionalidad:</span>
                        <span class="text-zinc-200">${escapeHtml(c.nationality || "N/A")}</span>
                    </div>
                    <div>
                        <span class="text-zinc-500 block text-[10px]">Emisión:</span>
                        <span class="text-zinc-400">${escapeHtml(c.issue_date || "N/A")}</span>
                    </div>
                    <div>
                        <span class="text-zinc-500 block text-[10px]">Vencimiento:</span>
                        <span class="text-zinc-400">${escapeHtml(c.expiry_date || "N/A")}</span>
                    </div>
                </div>
            `;
            credentialsContainer.appendChild(card);
        });
    }

    function renderSignaturesAndMetadata(metadata, signatures) {
        // Metadatos globales
        globalMetadataContent.innerHTML = `
            <div>
                <span class="text-zinc-500 block text-[11px]">Título Oficial:</span>
                <strong class="text-zinc-100 text-xs">${escapeHtml(metadata.document_title || "No consignado")}</strong>
            </div>
            <div>
                <span class="text-zinc-500 block text-[11px]">Folio o N° Expediente:</span>
                <strong class="text-zinc-200 font-mono text-xs">${escapeHtml(metadata.folio_or_id || "N/A")}</strong>
            </div>
            <div>
                <span class="text-zinc-500 block text-[11px]">Entidad Emisora:</span>
                <span class="text-zinc-300 text-xs">${escapeHtml(metadata.issuing_entity || "No consignada")}</span>
            </div>
            <div>
                <span class="text-zinc-500 block text-[11px]">Fecha del Documento:</span>
                <span class="text-zinc-300 text-xs">${escapeHtml(metadata.document_date || "N/A")}</span>
            </div>
        `;

        // Firmas y Sellos
        signaturesContainer.innerHTML = "";
        if (!signatures || signatures.length === 0) {
            signaturesContainer.innerHTML = `
                <div class="col-span-full p-6 text-center rounded-lg bg-zinc-900/30 border border-zinc-800 text-zinc-500 text-xs font-mono">
                    No se detectaron firmas ni sellos en el documento analizado.
                </div>
            `;
            return;
        }

        signatures.forEach(s => {
            const card = document.createElement("div");
            card.className = "bg-zinc-900/50 border border-zinc-800 rounded-lg p-3.5 space-y-2 text-xs";

            let tagsHtml = "";
            if (s.has_physical_signature) tagsHtml += `<span class="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700 text-[10px] font-mono">Firma Manuscrita</span> `;
            if (s.has_stamp_or_seal) tagsHtml += `<span class="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700 text-[10px] font-mono">Sello / Timbre</span> `;
            if (s.is_digital_certificate) tagsHtml += `<span class="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700 text-[10px] font-mono">Certificado Digital</span> `;

            card.innerHTML = `
                <div class="flex items-center justify-between">
                    <strong class="text-zinc-100 text-xs font-semibold">${escapeHtml(s.signer_name || "Firmante no identificado")}</strong>
                    <div class="flex gap-1">${tagsHtml}</div>
                </div>
                <p class="text-zinc-400 text-[11px]">${escapeHtml(s.signer_role_or_title || "Cargo no especificado")}</p>
                ${s.stamp_text ? `<p class="p-2 rounded bg-zinc-950 border border-zinc-800/90 text-zinc-300 text-[11px] font-mono">"${escapeHtml(s.stamp_text)}"</p>` : ""}
            `;
            signaturesContainer.appendChild(card);
        });
    }

    function renderPages(pages) {
        pagesContainer.innerHTML = "";

        pages.forEach(p => {
            const pageCard = document.createElement("div");
            pageCard.className = "bg-zinc-900/40 border border-zinc-800 rounded-lg p-4 space-y-3";

            let anomaliesHtml = "";
            if (p.visual_anomalies && p.visual_anomalies.length > 0) {
                anomaliesHtml = `
                    <div class="p-2.5 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300 text-xs flex items-center gap-2">
                        <svg class="w-4 h-4 text-amber-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.008v.008H12v-.008z"/>
                        </svg>
                        <span><strong>Anomalías Visuales:</strong> ${p.visual_anomalies.map(escapeHtml).join(", ")}</span>
                    </div>
                `;
            }

            let blocksSummaryHtml = `<div class="space-y-1.5 pt-2">`;
            p.blocks.forEach(b => {
                let badgeColor = "bg-zinc-800 text-zinc-300 border border-zinc-700";
                if (b.block_type === "table") badgeColor = "bg-zinc-800/90 text-zinc-200 border border-zinc-600";
                if (b.block_type === "identity_credential") badgeColor = "bg-zinc-800/90 text-zinc-200 border border-zinc-600";
                if (b.block_type === "stamp_signature") badgeColor = "bg-zinc-800/90 text-zinc-200 border border-zinc-600";

                blocksSummaryHtml += `
                    <div class="flex items-center justify-between text-xs px-3 py-1.5 rounded bg-zinc-950 border border-zinc-800/80 font-mono">
                        <div class="flex items-center gap-2">
                            <span class="text-zinc-500 font-semibold">#${b.reading_order_index}</span>
                            <span class="px-2 py-0.5 rounded text-[10px] font-medium ${badgeColor}">${escapeHtml(b.block_type)}</span>
                        </div>
                        <span class="text-zinc-500 text-[11px]">Confianza: ${(b.confidence * 100).toFixed(0)}%</span>
                    </div>
                `;
            });
            blocksSummaryHtml += `</div>`;

            pageCard.innerHTML = `
                <div class="flex items-center justify-between border-b border-zinc-800 pb-2">
                    <h4 class="text-xs font-semibold text-zinc-100 font-mono">Página ${p.page_number}</h4>
                    <span class="text-xs font-mono text-zinc-500">${p.blocks.length} bloques clasificados</span>
                </div>
                ${p.page_summary ? `<p class="text-xs text-zinc-300 italic">${escapeHtml(p.page_summary)}</p>` : ""}
                ${anomaliesHtml}
                ${blocksSummaryHtml}
            `;
            pagesContainer.appendChild(pageCard);
        });
    }

    // =================================================================
    // Tab Switching Logic (Neutral Slate/Zinc State)
    // =================================================================

    const tabButtons = document.querySelectorAll(".tab-btn");
    const tabContents = document.querySelectorAll(".tab-content");

    tabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetTab = btn.getAttribute("data-tab");

            tabButtons.forEach(b => {
                b.classList.remove("border-zinc-200", "text-zinc-100");
                b.classList.add("border-transparent", "text-zinc-400");
            });

            btn.classList.add("border-zinc-200", "text-zinc-100");
            btn.classList.remove("border-transparent", "text-zinc-400");

            tabContents.forEach(content => {
                if (content.id === targetTab) {
                    content.classList.remove("hidden");
                } else {
                    content.classList.add("hidden");
                }
            });
        });
    });

    // =================================================================
    // Copy JSON to Clipboard
    // =================================================================

    btnCopyJson.addEventListener("click", () => {
        if (!lastResultPayload) return;
        navigator.clipboard.writeText(JSON.stringify(lastResultPayload, null, 2)).then(() => {
            copyBtnText.textContent = "¡Copiado!";
            setTimeout(() => {
                copyBtnText.textContent = "Copiar JSON";
            }, 2000);
        }).catch(err => console.error("Error al copiar al portapapeles:", err));
    });

    // =================================================================
    // Helper Utilities
    // =================================================================

    function showError(title, message) {
        errorAlertTitle.textContent = title;
        errorAlertMessage.textContent = message;
        errorAlert.classList.remove("hidden");
        errorAlert.scrollIntoView({ behavior: "smooth" });
    }

    function hideError() {
        errorAlert.classList.add("hidden");
    }

    function escapeHtml(str) {
        if (typeof str !== "string") return str;
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
});
