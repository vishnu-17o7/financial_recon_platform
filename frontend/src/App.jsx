import { useEffect, useMemo, useState } from "react";

import { scenarioOptions } from "./constants/options";
import {
  checkHealth,
  getJobResults,
  reconcileWithMapping,
  runSecondPass,
  suggestColumnMapping
} from "./services/api";

const PAGE_UPLOAD = "upload";
const PAGE_MAPPING = "mapping";
const PAGE_SUMMARY = "summary";
const PAGE_RESULTS = "results";
const STAGE_ORDER = [PAGE_UPLOAD, PAGE_MAPPING, PAGE_SUMMARY, PAGE_RESULTS];

const DEFAULT_LOCALE = "en";
const SUPPORTED_LOCALES = [
  { value: "en", label: "EN" },
  { value: "es", label: "ES" }
];

const ACCEPTED_FILE_EXTENSIONS = [".csv", ".xlsx", ".xls"];
const MAX_UPLOAD_SIZE_MB = 25;
const MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024;

const TOAST_TIMEOUT_MS = 3200;
const TOAST_MESSAGE_MAX = 220;
const STEP_DELAY_MS = 260;
const RUN_HISTORY_STORAGE_KEY = "recon-run-history";
const RUN_HISTORY_LIMIT = 120;
const RUN_HISTORY_SNAPSHOT_LIMIT = 20;

const TRANSLATIONS = {
  es: {
    "Checking...": "Comprobando...",
    "System Ready": "Sistema listo",
    Offline: "Sin conexion",
    Language: "Idioma",
    "Financial Reconciliation": "Conciliacion financiera",
    "AI-powered mapping and discrepancy review": "Mapeo con IA y revision de discrepancias",
    "Switch to Light Mode": "Cambiar a modo claro",
    "Switch to Dark Mode": "Cambiar a modo oscuro",
    Logs: "Registros",
    Light: "Claro",
    Dark: "Oscuro",
    "Workflow stages": "Etapas del flujo",
    Upload: "Carga",
    "Mapping Diff": "Diferencia de mapeo",
    Summary: "Resumen",
    Results: "Resultados",
    "Upload Source Files": "Cargar archivos de origen",
    "Analyze and Continue": "Analizar y continuar",
    "Processing...": "Procesando...",
    "Scenario Type": "Tipo de escenario",
    "Analyst Name": "Nombre del analista",
    "Your name": "Tu nombre",
    "Left Source Label": "Etiqueta de origen izquierdo",
    "Right Source Label": "Etiqueta de origen derecho",
    "Drop or click to upload": "Suelta o haz clic para cargar",
    "Column Mapping Diff": "Diferencia de mapeo de columnas",
    "Back to Upload": "Volver a carga",
    "Run Reconciliation": "Ejecutar conciliacion",
    "Merge Conflict Style Mapping": "Mapeo estilo conflicto de fusion",
    "Resolve each field by selecting the matching columns on both sides.": "Resuelve cada campo seleccionando columnas coincidentes en ambos lados.",
    Required: "Requerido",
    Manual: "Manual",
    "No mapping suggestions were returned.": "No se devolvieron sugerencias de mapeo.",
    "Run mapping from the upload page first.": "Ejecuta primero el mapeo desde la pagina de carga.",
    "Reconciliation Results": "Resultados de conciliacion",
    "Summary Overview": "Resumen general",
    "View Detailed Results": "Ver resultados detallados",
    "Back to Summary": "Volver al resumen",
    "Back to Mapping": "Volver a mapeo",
    "Mapping Issues Detected": "Problemas de mapeo detectados",
    "Left Records": "Registros izquierdos",
    "Right Records": "Registros derechos",
    Matches: "Coincidencias",
    Exceptions: "Excepciones",
    "Match Rate": "Tasa de coincidencia",
    "Matched Transactions": "Transacciones conciliadas",
    "Match ID": "ID de coincidencia",
    Left: "Izquierda",
    Right: "Derecha",
    "Amount Delta": "Diferencia de monto",
    "Date Delta": "Diferencia de fecha",
    Status: "Estado",
    "No matches found": "No se encontraron coincidencias",
    "Discrepancy Inspector": "Inspector de discrepancias",
    Aligned: "Alineado",
    "All matched pairs are aligned.": "Todos los pares coincidentes estan alineados.",
    "Match Details: {id}": "Detalles de coincidencia: {id}",
    "Side-by-side snapshot comparison": "Comparacion lado a lado",
    "Detected Discrepancies": "Discrepancias detectadas",
    "No discrepancies found for this match.": "No se encontraron discrepancias para esta coincidencia.",
    "Select a matched pair to inspect differences.": "Selecciona un par para inspeccionar diferencias.",
    "Unmatched / Exception Transactions": "Transacciones sin coincidir / excepciones",
    ID: "ID",
    Transaction: "Transaccion",
    Reason: "Razon",
    "Recommended Action": "Accion recomendada",
    "Review source data and mapping": "Revisa los datos de origen y el mapeo",
    "No exceptions. All transactions matched.": "Sin excepciones. Todas las transacciones coinciden.",
    "Run reconciliation from the mapping page first.": "Ejecuta la conciliacion desde la pagina de mapeo.",
    "No data available": "No hay datos disponibles",
    "{count} rows": "{count} filas",
    "Left Column": "Columna izquierda",
    "Right Column": "Columna derecha",
    "-- Not mapped --": "-- Sin mapear --",
    "Resolve Mapping": "Resolver mapeo",
    "Process Logs": "Registros del proceso",
    "No logs yet. Run a process to see logs.": "Aun no hay registros. Ejecuta un proceso para verlos.",
    "Clear Logs": "Limpiar registros",
    Close: "Cerrar",
    "Please upload both files to continue": "Carga ambos archivos para continuar",
    "Complete mapping before running reconciliation": "Completa el mapeo antes de ejecutar la conciliacion",
    "Map at least one left and right column pair before reconciliation": "Mapea al menos un par de columnas antes de conciliar",
    "Starting column mapping process...": "Iniciando proceso de mapeo de columnas...",
    "Analyzing column structures...": "Analizando estructuras de columnas...",
    "Running AI column mapping...": "Ejecutando mapeo de columnas con IA...",
    "Sending request to LLM for column mapping suggestions...": "Enviando solicitud al LLM para sugerencias de mapeo...",
    "Received {count} mapping suggestions from LLM": "Se recibieron {count} sugerencias de mapeo del LLM",
    "Mapping summary: {mapped} fields mapped, {unmapped} fields unmapped": "Resumen: {mapped} mapeados, {unmapped} sin mapear",
    "Column mapping completed successfully!": "Mapeo de columnas completado correctamente",
    "AI mapping is ready for review": "El mapeo de IA esta listo para revision",
    "Mapping failed: {error}": "Fallo de mapeo: {error}",
    "Starting reconciliation process...": "Iniciando proceso de conciliacion...",
    "Left source: {value}": "Origen izquierdo: {value}",
    "Right source: {value}": "Origen derecho: {value}",
    "Reading and parsing files...": "Leyendo y analizando archivos...",
    "Parsing left file: {name}": "Analizando archivo izquierdo: {name}",
    "Parsing right file: {name}": "Analizando archivo derecho: {name}",
    "Normalizing left file data...": "Normalizando archivo izquierdo...",
    "Normalizing right file data...": "Normalizando archivo derecho...",
    "Running transaction matching algorithm...": "Ejecutando algoritmo de coincidencia...",
    "Running AI-powered transaction matching...": "Ejecutando coincidencia impulsada por IA...",
    "Matching complete: {count} matches found": "Coincidencia completa: {count} encontradas",
    "Exceptions: {count} unmatched transactions": "Excepciones: {count} transacciones sin coincidir",
    "Detecting discrepancies and building results...": "Detectando discrepancias y armando resultados...",
    "Analyzing discrepancies...": "Analizando discrepancias...",
    "Found {count} transactions with discrepancies": "Se encontraron {count} transacciones con discrepancias",
    "Reconciliation completed successfully!": "Conciliacion completada correctamente",
    "Mapping validation failed; review issues in results": "La validacion de mapeo fallo; revisa los resultados",
    "Mapping validation failed: {count} issue(s)": "La validacion de mapeo fallo: {count} problema(s)",
    "Mapping issue ({side}/{field}): {message}": "Problema de mapeo ({side}/{field}): {message}",
    "Reconciliation complete: {count} matches": "Conciliacion completa: {count} coincidencias",
    "Reconciliation failed: {error}": "La conciliacion fallo: {error}",
    "Retry Unmatched with LLM": "Reintentar no conciliadas con LLM",
    "Running second-pass LLM on unmatched exceptions...": "Ejecutando segundo pase LLM en excepciones no conciliadas...",
    "Second-pass completed: {count} additional matches": "Segundo pase completado: {count} coincidencias adicionales",
    "Second-pass failed: {error}": "Segundo pase fallido: {error}",
    "Load this run and replace the current workspace state?": "¿Cargar esta corrida y reemplazar el estado actual del espacio de trabajo?",
    "History replay used local snapshot because live results failed: {error}": "La reproduccion uso una instantanea local porque fallaron los resultados en vivo: {error}",
    "Unable to load this run: {error}": "No se pudo cargar esta corrida: {error}",
    "This history entry does not have replayable details yet": "Esta entrada de historial aun no tiene detalles reproducibles",
    "Loaded historical run from {time}": "Corrida historica cargada desde {time}",
    "Historical run loaded successfully": "Corrida historica cargada correctamente",
    Load: "Cargar",
    "Load Run": "Cargar corrida",
    Action: "Accion",
    "Load this run into workspace": "Cargar esta corrida en el espacio de trabajo",
    "Loading...": "Cargando...",
    "Export Results CSV": "Exportar resultados CSV",
    "No reconciliation results available to export": "No hay resultados de conciliacion para exportar",
    "Results exported to {file}": "Resultados exportados a {file}",
    "Export failed: {error}": "La exportacion fallo: {error}",
    "Connection failed: {error}": "Fallo de conexion: {error}",
    "{side} file type is not supported. Upload CSV or Excel files.": "El archivo de {side} no es compatible. Carga CSV o Excel.",
    "{side} file is empty. Upload a non-empty file.": "El archivo de {side} esta vacio. Carga uno no vacio.",
    "{side} file exceeds {size} MB.": "El archivo de {side} supera {size} MB.",
    "Reading {side} file: {name} ({size} KB)": "Leyendo archivo de {side}: {name} ({size} KB)",
    "issue(s)": "problema(s)",
    diffs: "diferencias",
    "Left source": "origen izquierdo",
    "Right source": "origen derecho",
    "No logs": "Sin registros"
  }
};

function detectPreferredLocale() {
  const savedLocale = localStorage.getItem("uiLocale");
  if (SUPPORTED_LOCALES.some((locale) => locale.value === savedLocale)) {
    return savedLocale;
  }

  const browserLocale = String(navigator.language || DEFAULT_LOCALE).slice(0, 2).toLowerCase();
  if (SUPPORTED_LOCALES.some((locale) => locale.value === browserLocale)) {
    return browserLocale;
  }

  return DEFAULT_LOCALE;
}

function translate(locale, text, params = {}) {
  const template = TRANSLATIONS[locale]?.[text] || text;

  return Object.entries(params).reduce((result, [key, value]) => {
    return result.replace(new RegExp(`\\{${key}\\}`, "g"), String(value ?? ""));
  }, template);
}

function normalizeTextInput(value, fallback) {
  const cleaned = String(value || "").trim();
  return cleaned || fallback;
}

function formatFileSizeKb(file, locale) {
  const sizeInKb = Number(file?.size || 0) / 1024;
  return sizeInKb.toLocaleString(locale, { maximumFractionDigits: 1 });
}

function getFileExtension(fileName) {
  const parts = String(fileName || "").toLowerCase().split(".");
  if (parts.length < 2) {
    return "";
  }

  return `.${parts.pop()}`;
}

function validateUploadFile(file, sideLabel, t) {
  if (!file) {
    return "";
  }

  const extension = getFileExtension(file.name);
  if (!ACCEPTED_FILE_EXTENSIONS.includes(extension)) {
    return t("{side} file type is not supported. Upload CSV or Excel files.", {
      side: sideLabel
    });
  }

  if (file.size <= 0) {
    return t("{side} file is empty. Upload a non-empty file.", {
      side: sideLabel
    });
  }

  if (file.size > MAX_UPLOAD_SIZE_BYTES) {
    return t("{side} file exceeds {size} MB.", {
      side: sideLabel,
      size: MAX_UPLOAD_SIZE_MB
    });
  }

  return "";
}

function toDisplayArray(value) {
  return Array.isArray(value) ? value : [];
}

function prepareMappingRows(rows) {
  const seen = new Map();

  return toDisplayArray(rows).map((row, index) => {
    const field = String(row?.field || `field_${index + 1}`);
    const ordinal = (seen.get(field) || 0) + 1;
    seen.set(field, ordinal);

    return {
      ...row,
      _rowKey: `${field}__${ordinal}`,
      field,
      label: String(row?.label || field),
      left_column: row?.left_column || null,
      right_column: row?.right_column || null,
      source: row?.source === "manual" ? "manual" : "ai",
      confidence: Number.isFinite(Number(row?.confidence)) ? Number(row.confidence) : 0,
      required: Boolean(row?.required)
    };
  });
}

function readRunHistoryFromStorage() {
  try {
    const raw = localStorage.getItem(RUN_HISTORY_STORAGE_KEY);
    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed.filter((entry) => entry && typeof entry === "object");
  } catch (_error) {
    return [];
  }
}

function normalizeReconciliationResult(response) {
  const payload = response && typeof response === "object" ? response : {};

  return {
    ...payload,
    mapping_issues: toDisplayArray(payload?.mapping_issues),
    matches: toDisplayArray(payload?.matches),
    discrepancies: toDisplayArray(payload?.discrepancies),
    exceptions: toDisplayArray(payload?.exceptions),
    classified_exceptions: toDisplayArray(payload?.classified_exceptions),
    journal_entries: toDisplayArray(payload?.journal_entries),
    reconciliation_summary:
      payload?.reconciliation_summary && typeof payload.reconciliation_summary === "object"
        ? payload.reconciliation_summary
        : null
  };
}

function withoutHistorySnapshots(entry) {
  if (!entry || typeof entry !== "object") {
    return entry;
  }

  const { inputSnapshot, resultSnapshot, ...rest } = entry;
  return rest;
}

function serializeMappingRows(rows) {
  return toDisplayArray(rows).map((row) => {
    const { _rowKey, ...rest } = row || {};
    return {
      ...rest,
      field: String(rest?.field || ""),
      label: String(rest?.label || rest?.field || ""),
      left_column: rest?.left_column || null,
      right_column: rest?.right_column || null,
      source: rest?.source === "manual" ? "manual" : "ai",
      confidence: Number.isFinite(Number(rest?.confidence)) ? Number(rest.confidence) : 0,
      required: Boolean(rest?.required)
    };
  });
}

function toUniqueStrings(values) {
  return Array.from(
    new Set(
      toDisplayArray(values)
        .map((value) => String(value || "").trim())
        .filter(Boolean)
    )
  );
}

function buildHistoryInputSnapshot({
  scenarioType,
  createdBy,
  leftLabel,
  rightLabel,
  leftFile,
  rightFile,
  mappingRows,
  mappingData
}) {
  const safeMappingData =
    mappingData && typeof mappingData === "object"
      ? {
          left: {
            ...(mappingData.left || {}),
            columns: toDisplayArray(mappingData?.left?.columns),
            preview_rows: toDisplayArray(mappingData?.left?.preview_rows)
          },
          right: {
            ...(mappingData.right || {}),
            columns: toDisplayArray(mappingData?.right?.columns),
            preview_rows: toDisplayArray(mappingData?.right?.preview_rows)
          }
        }
      : null;

  return {
    scenarioType,
    createdBy,
    leftLabel,
    rightLabel,
    leftFileName: String(leftFile?.name || ""),
    rightFileName: String(rightFile?.name || ""),
    mappingRows: serializeMappingRows(mappingRows),
    mappingData: safeMappingData
  };
}

function buildHistoryResultSnapshot(result) {
  const normalized = normalizeReconciliationResult(result);
  return {
    job_id: String(normalized?.job_id || ""),
    status: String(normalized?.status || ""),
    metrics:
      normalized?.metrics && typeof normalized.metrics === "object"
        ? normalized.metrics
        : {},
    mapping_issues: normalized.mapping_issues,
    matches: normalized.matches,
    discrepancies: normalized.discrepancies,
    exceptions: normalized.exceptions,
    classified_exceptions: normalized.classified_exceptions,
    journal_entries: normalized.journal_entries,
    reconciliation_summary: normalized.reconciliation_summary,
    exception_buckets:
      normalized?.exception_buckets && typeof normalized.exception_buckets === "object"
        ? normalized.exception_buckets
        : {},
    left_file:
      normalized?.left_file && typeof normalized.left_file === "object"
        ? normalized.left_file
        : null,
    right_file:
      normalized?.right_file && typeof normalized.right_file === "object"
        ? normalized.right_file
        : null
  };
}

function buildReplayMappingData(inputSnapshot) {
  if (!inputSnapshot || typeof inputSnapshot !== "object") {
    return null;
  }

  const mappingData =
    inputSnapshot.mappingData && typeof inputSnapshot.mappingData === "object"
      ? inputSnapshot.mappingData
      : {};
  const leftSnapshot =
    mappingData.left && typeof mappingData.left === "object"
      ? mappingData.left
      : {};
  const rightSnapshot =
    mappingData.right && typeof mappingData.right === "object"
      ? mappingData.right
      : {};

  const mappingRows = serializeMappingRows(inputSnapshot.mappingRows);
  const inferredLeftColumns = toUniqueStrings(mappingRows.map((row) => row.left_column));
  const inferredRightColumns = toUniqueStrings(mappingRows.map((row) => row.right_column));

  return {
    ...mappingData,
    left: {
      ...leftSnapshot,
      file_name: String(leftSnapshot.file_name || inputSnapshot.leftFileName || ""),
      columns: toDisplayArray(leftSnapshot.columns).length
        ? toDisplayArray(leftSnapshot.columns)
        : inferredLeftColumns,
      preview_rows: toDisplayArray(leftSnapshot.preview_rows)
    },
    right: {
      ...rightSnapshot,
      file_name: String(rightSnapshot.file_name || inputSnapshot.rightFileName || ""),
      columns: toDisplayArray(rightSnapshot.columns).length
        ? toDisplayArray(rightSnapshot.columns)
        : inferredRightColumns,
      preview_rows: toDisplayArray(rightSnapshot.preview_rows)
    }
  };
}

function escapeCsvCell(value) {
  if (value === null || value === undefined) {
    return "";
  }

  const serialized =
    typeof value === "string"
      ? value
      : typeof value === "number" || typeof value === "boolean"
        ? String(value)
        : JSON.stringify(value);

  const text = String(serialized ?? "");
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }

  return text;
}

function rowsToCsv(rows) {
  const items = toDisplayArray(rows);
  if (!items.length) {
    return "section,message\nmeta,No result rows";
  }

  const headers = [];
  const headerSet = new Set();
  items.forEach((row) => {
    Object.keys(row || {}).forEach((key) => {
      if (!headerSet.has(key)) {
        headerSet.add(key);
        headers.push(key);
      }
    });
  });

  const lines = [headers.map(escapeCsvCell).join(",")];
  items.forEach((row) => {
    const line = headers.map((header) => escapeCsvCell(row?.[header])).join(",");
    lines.push(line);
  });

  return lines.join("\n");
}

function triggerCsvDownload(fileName, csvText) {
  const blob = new Blob(["\uFEFF", csvText], { type: "text/csv;charset=utf-8;" });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");

  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();

  window.URL.revokeObjectURL(url);
}

function buildResultExportRows(result, { leftLabel, rightLabel }) {
  const normalized = normalizeReconciliationResult(result);
  const rows = [];

  rows.push(
    {
      section: "meta",
      key: "generated_at",
      value: new Date().toISOString()
    },
    {
      section: "meta",
      key: "job_id",
      value: String(normalized?.job_id || "")
    },
    {
      section: "meta",
      key: "status",
      value: String(normalized?.status || "")
    },
    {
      section: "meta",
      key: "left_label",
      value: String(leftLabel || "")
    },
    {
      section: "meta",
      key: "right_label",
      value: String(rightLabel || "")
    }
  );

  Object.entries(normalized?.metrics || {}).forEach(([key, value]) => {
    rows.push({ section: "metrics", key, value });
  });

  toDisplayArray(normalized.mapping_issues).forEach((issue, index) => {
    rows.push({
      section: "mapping_issues",
      index: index + 1,
      severity: String(issue?.severity || ""),
      side: String(issue?.side || ""),
      field: String(issue?.field || ""),
      message: String(issue?.message || "")
    });
  });

  toDisplayArray(normalized.matches).forEach((match, index) => {
    rows.push({
      section: "matches",
      index: index + 1,
      match_id: String(match?.id || match?.match_id || ""),
      left_transaction_id: String(
        match?.left?.id || match?.a || match?.left_transaction_id || ""
      ),
      right_transaction_id: String(
        match?.right?.id || match?.b || match?.right_transaction_id || ""
      ),
      amount_delta: match?.amount_delta ?? "",
      date_delta_days: match?.date_delta_days ?? "",
      algorithm: String(match?.algo || ""),
      confidence: match?.confidence ?? "",
      status: String(match?.status || "")
    });
  });

  toDisplayArray(normalized.discrepancies).forEach((item, index) => {
    rows.push({
      section: "discrepancies",
      index: index + 1,
      match_id: String(item?.match_id || ""),
      issues_count: toDisplayArray(item?.issues).length,
      issues: JSON.stringify(toDisplayArray(item?.issues)),
      left_snapshot: JSON.stringify(item?.left_snapshot || {}),
      right_snapshot: JSON.stringify(item?.right_snapshot || {})
    });
  });

  toDisplayArray(normalized.exceptions).forEach((exception, index) => {
    rows.push({
      section: "exceptions",
      index: index + 1,
      exception_id: String(exception?.id || ""),
      transaction_id: String(
        exception?.transaction?.transaction_id || exception?.txn || ""
      ),
      status: String(exception?.status || ""),
      reason: String(exception?.reason || ""),
      recommended_action: String(exception?.recommended_action || "")
    });
  });

  toDisplayArray(normalized.classified_exceptions).forEach((entry, index) => {
    rows.push({
      section: "classified_exceptions",
      index: index + 1,
      exception_id: String(entry?.exception_id || ""),
      transaction_id: String(entry?.transaction_id || ""),
      bucket: String(entry?.bucket_label || entry?.bucket_key || ""),
      operation: String(entry?.operation || ""),
      amount: entry?.amount ?? "",
      confidence: entry?.confidence ?? "",
      rationale: String(entry?.rationale || "")
    });
  });

  toDisplayArray(normalized.journal_entries).forEach((entry, index) => {
    rows.push({
      section: "journal_entries",
      index: index + 1,
      entry_id: String(entry?.entry_id || ""),
      entry_date: String(entry?.entry_date || ""),
      debit_account: String(entry?.debit_account || ""),
      credit_account: String(entry?.credit_account || ""),
      amount: entry?.amount ?? "",
      narration: String(entry?.narration || "")
    });
  });

  const summary =
    normalized?.reconciliation_summary && typeof normalized.reconciliation_summary === "object"
      ? normalized.reconciliation_summary
      : null;
  if (summary) {
    rows.push(
      {
        section: "summary_balance",
        side: "left",
        label: String(leftLabel || "left"),
        unadjusted_closing_balance: summary?.bank_statement?.unadjusted_closing_balance ?? "",
        adjusted_closing_balance: summary?.bank_statement?.adjusted_closing_balance ?? ""
      },
      {
        section: "summary_balance",
        side: "right",
        label: String(rightLabel || "right"),
        unadjusted_closing_balance: summary?.cash_book?.unadjusted_closing_balance ?? "",
        adjusted_closing_balance: summary?.cash_book?.adjusted_closing_balance ?? ""
      },
      {
        section: "summary_balance",
        side: "overall",
        unreconciled_amount: summary?.unreconciled_amount ?? ""
      }
    );

    toDisplayArray(summary?.bank_statement?.adjustments).forEach((item, index) => {
      rows.push({
        section: "summary_adjustments",
        index: index + 1,
        side: "bank_statement",
        bucket_key: String(item?.bucket_key || ""),
        label: String(item?.label || ""),
        operation: String(item?.operation || ""),
        amount: item?.amount ?? ""
      });
    });

    toDisplayArray(summary?.cash_book?.adjustments).forEach((item, index) => {
      rows.push({
        section: "summary_adjustments",
        index: index + 1,
        side: "cash_book",
        bucket_key: String(item?.bucket_key || ""),
        label: String(item?.label || ""),
        operation: String(item?.operation || ""),
        amount: item?.amount ?? ""
      });
    });
  }

  return rows;
}

function ConfidenceBar({ confidence }) {
  const percent = Math.max(0, Math.min(100, Math.round((Number(confidence) || 0) * 100)));
  let level = "low";
  if (percent >= 70) {
    level = "high";
  } else if (percent >= 40) {
    level = "medium";
  }

  return (
    <div className="confidence-bar">
      <div className="confidence-fill">
        <div className={`confidence-fill-inner confidence-${level}`} style={{ width: `${percent}%` }} />
      </div>
      <span className="confidence-text">{percent}%</span>
    </div>
  );
}

function renderPreviewTable(section, tone, { t, formatNumber }) {
  const columns = toDisplayArray(section?.columns);
  const previewRows = toDisplayArray(section?.preview_rows);

  if (!columns.length) {
    return <div className="empty-state">{t("No data available")}</div>;
  }

  const fileName = String(section?.file_name || "-");
  const rowCount = Number.isFinite(Number(section?.row_count)) ? Number(section.row_count) : previewRows.length;

  return (
    <div className={`file-preview file-preview-${tone}`}>
      <div className="file-preview-head">
        <h3 title={fileName}>{fileName}</h3>
        <span>{t("{count} rows", { count: formatNumber(rowCount) })}</span>
      </div>
      <div className="file-preview-table-wrap">
        <table className="file-preview-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {previewRows.map((row, rowIndex) => (
              <tr key={`${fileName}-${rowIndex}`}>
                {columns.map((column) => {
                  const value = String(row?.[column] ?? "");
                  return (
                    <td key={`${fileName}-${rowIndex}-${column}`} className="cell-ellipsis" title={value}>
                      {value}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function App({ darkMode = false, onToggleDarkMode = () => {}, onNavigateHome = () => {} }) {
  const [locale, setLocale] = useState(() => detectPreferredLocale());
  const [connection, setConnection] = useState({ ok: true, checking: true });

  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [reconcileLoading, setReconcileLoading] = useState(false);
  const [secondPassLoading, setSecondPassLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(PAGE_UPLOAD);
  const [processingStep, setProcessingStep] = useState("");

  const [scenarioType, setScenarioType] = useState("bank_gl");
  const [createdBy, setCreatedBy] = useState("analyst");
  const [leftLabel, setLeftLabel] = useState("Bank Statement");
  const [rightLabel, setRightLabel] = useState("GL Records");
  const [leftFile, setLeftFile] = useState(null);
  const [rightFile, setRightFile] = useState(null);

  const [mappingData, setMappingData] = useState(null);
  const [mappingRows, setMappingRows] = useState([]);
  const [reconResult, setReconResult] = useState(null);
  const [selectedDiscrepancyId, setSelectedDiscrepancyId] = useState("");

  const [toast, setToast] = useState({ message: "", kind: "info" });
  const [logs, setLogs] = useState([]);
  const [showLogs, setShowLogs] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [historyLoadingId, setHistoryLoadingId] = useState("");
  const [runHistory, setRunHistory] = useState(() => readRunHistoryFromStorage());
  const [showOnboarding, setShowOnboarding] = useState(() => {
    const seen = localStorage.getItem("recon-onboarding-dismissed");
    return seen !== "true";
  });
  const [pageTransitioning, setPageTransitioning] = useState(false);

  const numberFormatter = useMemo(() => new Intl.NumberFormat(locale), [locale]);
  const decimalFormatter = useMemo(
    () => new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }),
    [locale]
  );

  const t = (text, params = {}) => translate(locale, text, params);
  const formatNumber = (value) => numberFormatter.format(Number(value || 0));
  const formatPercent = (value) => `${decimalFormatter.format(Number(value || 0))}%`;
  const formatAmount = (value) => decimalFormatter.format(Number(value || 0));

  const connectionLabel = connection.checking
    ? t("Checking...")
    : connection.ok
      ? t("System Ready")
      : t("Offline");

  useEffect(() => {
    localStorage.setItem("uiLocale", locale);

    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    if (!showLogs && !showHistory) {
      return undefined;
    }

    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        setShowLogs(false);
        setShowHistory(false);
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [showLogs, showHistory]);

  useEffect(() => {
    setPageTransitioning(true);
    const timer = window.setTimeout(() => {
      setPageTransitioning(false);
    }, 420);

    return () => window.clearTimeout(timer);
  }, [currentPage]);

  function addLog(message, type = "info") {
    const timestamp = new Date().toLocaleTimeString(locale);
    setLogs((prev) => [...prev, { timestamp, message, type }]);
  }

  function clearLogs() {
    setLogs([]);
  }

  function dismissOnboarding() {
    setShowOnboarding(false);
    localStorage.setItem("recon-onboarding-dismissed", "true");
  }

  function appendRunHistory(entry) {
    setRunHistory((current) => {
      const bounded = [entry, ...current].slice(0, RUN_HISTORY_LIMIT);
      const next = bounded.map((item, index) => {
        if (index < RUN_HISTORY_SNAPSHOT_LIMIT) {
          return item;
        }
        return withoutHistorySnapshots(item);
      });
      localStorage.setItem(RUN_HISTORY_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }

  function clearRunHistory() {
    setRunHistory([]);
    localStorage.removeItem(RUN_HISTORY_STORAGE_KEY);
  }

  useEffect(() => {
    let mounted = true;

    setConnection({ ok: true, checking: true });
    checkHealth()
      .then(() => {
        if (!mounted) {
          return;
        }
        setConnection({ ok: true, checking: false });
      })
      .catch((error) => {
        if (!mounted) {
          return;
        }

        setConnection({ ok: false, checking: false });
        const detail = error?.message || "Unknown error";
        showToast(t("Connection failed: {error}", { error: detail }), "error");
      });

    return () => {
      mounted = false;
    };
    // Locale changes should also refresh user-facing connection messages.
  }, [locale]);

  useEffect(() => {
    if (!toast.message) {
      return undefined;
    }

    const timer = window.setTimeout(() => {
      setToast({ message: "", kind: "info" });
    }, TOAST_TIMEOUT_MS);

    return () => window.clearTimeout(timer);
  }, [toast.message]);

  function showToast(message, kind = "info") {
    const normalizedMessage = String(message || "").trim();
    if (!normalizedMessage) {
      return;
    }

    const safeMessage =
      normalizedMessage.length > TOAST_MESSAGE_MAX
        ? `${normalizedMessage.slice(0, TOAST_MESSAGE_MAX - 3)}...`
        : normalizedMessage;

    setToast({ message: safeMessage, kind });
  }

  function goToPage(nextPage) {
    if (nextPage === PAGE_MAPPING && !mappingData) {
      return;
    }
    if ((nextPage === PAGE_SUMMARY || nextPage === PAGE_RESULTS) && !reconResult) {
      return;
    }
    setCurrentPage(nextPage);
  }

  function updateMapping(rowKey, key, value) {
    setMappingRows((current) =>
      current.map((item) => {
        if (item._rowKey !== rowKey) {
          return item;
        }

        return {
          ...item,
          [key]: value || null,
          source: "manual"
        };
      })
    );
  }

  function handleFileSelect(side, event) {
    const selectedFile = event.target.files?.[0] || null;

    if (!selectedFile) {
      if (side === "left") {
        setLeftFile(null);
      } else {
        setRightFile(null);
      }
      return;
    }

    const sideLabel = side === "left" ? t("Left source") : t("Right source");
    const validationError = validateUploadFile(selectedFile, sideLabel, t);
    if (validationError) {
      showToast(validationError, "error");
      addLog(validationError, "error");
      event.target.value = "";
      return;
    }

    if (side === "left") {
      setLeftFile(selectedFile);
    } else {
      setRightFile(selectedFile);
    }
  }

  async function handleSuggestMapping(event) {
    event.preventDefault();

    if (!leftFile || !rightFile) {
      showToast(t("Please upload both files to continue"), "error");
      return;
    }

    clearLogs();
    setSuggestionLoading(true);
    addLog(t("Starting column mapping process..."), "info");

    try {
      addLog(
        t("Reading {side} file: {name} ({size} KB)", {
          side: t("Left"),
          name: leftFile.name,
          size: formatFileSizeKb(leftFile, locale)
        }),
        "info"
      );
      addLog(
        t("Reading {side} file: {name} ({size} KB)", {
          side: t("Right"),
          name: rightFile.name,
          size: formatFileSizeKb(rightFile, locale)
        }),
        "info"
      );
      addLog(t("Analyzing column structures..."), "info");

      setProcessingStep(t("Running AI column mapping..."));
      addLog(t("Sending request to LLM for column mapping suggestions..."), "info");

      const response = await suggestColumnMapping({
        scenarioType,
        leftFile,
        rightFile
      });

      const preparedRows = prepareMappingRows(response?.suggestions);
      const mappedFields = preparedRows.filter((row) => row.left_column && row.right_column).length;
      const unmappedFields = preparedRows.length - mappedFields;

      addLog(
        t("Received {count} mapping suggestions from LLM", {
          count: formatNumber(preparedRows.length)
        }),
        "success"
      );
      addLog(
        t("Mapping summary: {mapped} fields mapped, {unmapped} fields unmapped", {
          mapped: formatNumber(mappedFields),
          unmapped: formatNumber(unmappedFields)
        }),
        "info"
      );

      const normalizedMappingData = {
        ...response,
        left: {
          ...(response?.left || {}),
          columns: toDisplayArray(response?.left?.columns),
          preview_rows: toDisplayArray(response?.left?.preview_rows)
        },
        right: {
          ...(response?.right || {}),
          columns: toDisplayArray(response?.right?.columns),
          preview_rows: toDisplayArray(response?.right?.preview_rows)
        }
      };

      setMappingData(normalizedMappingData);
      setMappingRows(preparedRows);
      setReconResult(null);
      setSelectedDiscrepancyId("");
      setCurrentPage(PAGE_MAPPING);
      setProcessingStep("");

      addLog(t("Column mapping completed successfully!"), "success");
      showToast(t("AI mapping is ready for review"), "success");

      if (!preparedRows.length) {
        showToast(t("No mapping suggestions were returned."), "error");
      }
    } catch (error) {
      const detail = error?.message || "Unknown error";
      addLog(`Error: ${detail}`, "error");
      setProcessingStep("");
      showToast(t("Mapping failed: {error}", { error: detail }), "error");
    } finally {
      setSuggestionLoading(false);
    }
  }

  async function handleRunReconciliation() {
    if (!leftFile || !rightFile || !mappingRows.length) {
      showToast(t("Complete mapping before running reconciliation"), "error");
      return;
    }

    const sanitizedCreatedBy = normalizeTextInput(createdBy, "analyst");
    const sanitizedLeftLabel = normalizeTextInput(leftLabel, "Left Source");
    const sanitizedRightLabel = normalizeTextInput(rightLabel, "Right Source");

    if (sanitizedCreatedBy !== createdBy) {
      setCreatedBy(sanitizedCreatedBy);
    }
    if (sanitizedLeftLabel !== leftLabel) {
      setLeftLabel(sanitizedLeftLabel);
    }
    if (sanitizedRightLabel !== rightLabel) {
      setRightLabel(sanitizedRightLabel);
    }

    const validMappings = mappingRows.filter(
      (row) => row.left_column || row.right_column
    );
    if (!validMappings.length) {
      showToast(t("Map at least one left and right column pair before reconciliation"), "error");
      return;
    }

    clearLogs();
    setReconcileLoading(true);
    const runStartedAt = Date.now();
    addLog(t("Starting reconciliation process..."), "info");
    addLog(t("Left source: {value}", { value: sanitizedLeftLabel }), "info");
    addLog(t("Right source: {value}", { value: sanitizedRightLabel }), "info");

    try {
      setProcessingStep(t("Reading and parsing files..."));
      addLog(t("Parsing left file: {name}", { name: leftFile.name }), "info");
      addLog(t("Parsing right file: {name}", { name: rightFile.name }), "info");
      await new Promise((resolve) => setTimeout(resolve, STEP_DELAY_MS));

      setProcessingStep(t("Normalizing left file data..."));
      addLog(t("Normalizing left file data..."), "info");
      await new Promise((resolve) => setTimeout(resolve, STEP_DELAY_MS));

      setProcessingStep(t("Normalizing right file data..."));
      addLog(t("Normalizing right file data..."), "info");
      await new Promise((resolve) => setTimeout(resolve, STEP_DELAY_MS));

      setProcessingStep(t("Running transaction matching algorithm..."));
      addLog(t("Running AI-powered transaction matching..."), "info");

      const response = await reconcileWithMapping({
        scenarioType,
        createdBy: sanitizedCreatedBy,
        leftLabel: sanitizedLeftLabel,
        rightLabel: sanitizedRightLabel,
        leftFile,
        rightFile,
        mapping: {
          mappings: validMappings.map(({ _rowKey, ...mapping }) => mapping)
        }
      });

      const normalizedResult = normalizeReconciliationResult(response);

      const isMappingFailed = normalizedResult.status === "mapping_failed";

      let discrepanciesCount = 0;
      if (!isMappingFailed) {
        addLog(
          t("Matching complete: {count} matches found", {
            count: formatNumber(normalizedResult.metrics?.matched_count || 0)
          }),
          "success"
        );
        addLog(
          t("Exceptions: {count} unmatched transactions", {
            count: formatNumber(normalizedResult.metrics?.exception_count || 0)
          }),
          "info"
        );

        setProcessingStep(t("Detecting discrepancies and building results..."));
        addLog(t("Analyzing discrepancies..."), "info");
        await new Promise((resolve) => setTimeout(resolve, STEP_DELAY_MS));

        discrepanciesCount = normalizedResult.discrepancies.filter(
          (item) => toDisplayArray(item?.issues).length > 0
        ).length;
        addLog(
          t("Found {count} transactions with discrepancies", {
            count: formatNumber(discrepanciesCount)
          }),
          discrepanciesCount > 0 ? "warning" : "success"
        );
      } else {
        const issueCount = toDisplayArray(normalizedResult.mapping_issues).length;
        addLog(
          t("Mapping validation failed: {count} issue(s)", {
            count: formatNumber(issueCount)
          }),
          "error"
        );
        toDisplayArray(normalizedResult.mapping_issues).forEach((issue) => {
          const side = String(issue?.side || "unknown").toUpperCase();
          const field = String(issue?.field || "unknown");
          const message = String(issue?.message || "");
          addLog(
            t("Mapping issue ({side}/{field}): {message}", {
              side,
              field,
              message,
            }),
            issue?.severity === "warning" ? "warning" : "error"
          );
        });
      }

      setReconResult(normalizedResult);
      setSelectedDiscrepancyId(String(normalizedResult.discrepancies[0]?.match_id || ""));
      setCurrentPage(isMappingFailed ? PAGE_RESULTS : PAGE_SUMMARY);
      setProcessingStep("");
      addLog(
        isMappingFailed
          ? t("Mapping validation failed; review issues in results")
          : t("Reconciliation completed successfully!"),
        isMappingFailed ? "error" : "success"
      );

      const inputSnapshot = buildHistoryInputSnapshot({
        scenarioType,
        createdBy: sanitizedCreatedBy,
        leftLabel: sanitizedLeftLabel,
        rightLabel: sanitizedRightLabel,
        leftFile,
        rightFile,
        mappingRows,
        mappingData
      });

      appendRunHistory({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        timestamp: new Date().toISOString(),
        scenarioType,
        analyst: sanitizedCreatedBy,
        leftSource: sanitizedLeftLabel,
        rightSource: sanitizedRightLabel,
        leftFileName: String(leftFile?.name || ""),
        rightFileName: String(rightFile?.name || ""),
        status: isMappingFailed ? "mapping_failed" : "completed",
        matches: Number(normalizedResult.metrics?.matched_count || 0),
        exceptions: Number(normalizedResult.metrics?.exception_count || 0),
        matchPct: Number(normalizedResult.metrics?.matched_pct || 0),
        discrepancyCount: Number(discrepanciesCount || 0),
        mappingIssueCount: Number(toDisplayArray(normalizedResult.mapping_issues).length || 0),
        durationMs: Math.max(Date.now() - runStartedAt, 0),
        jobId: String(normalizedResult?.job_id || ""),
        inputSnapshot,
        resultSnapshot: buildHistoryResultSnapshot(normalizedResult)
      });

      if (normalizedResult.status === "mapping_failed") {
        showToast(t("Mapping validation failed; review issues in results"), "error");
      } else {
        showToast(
          t("Reconciliation complete: {count} matches", {
            count: formatNumber(normalizedResult.metrics?.matched_count || 0)
          }),
          "success"
        );
      }
    } catch (error) {
      const detail = error?.message || "Unknown error";
      addLog(`Error: ${detail}`, "error");
      setProcessingStep("");
      showToast(t("Reconciliation failed: {error}", { error: detail }), "error");
      const inputSnapshot = buildHistoryInputSnapshot({
        scenarioType,
        createdBy: sanitizedCreatedBy,
        leftLabel: sanitizedLeftLabel,
        rightLabel: sanitizedRightLabel,
        leftFile,
        rightFile,
        mappingRows,
        mappingData
      });

      appendRunHistory({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        timestamp: new Date().toISOString(),
        scenarioType,
        analyst: sanitizedCreatedBy,
        leftSource: sanitizedLeftLabel,
        rightSource: sanitizedRightLabel,
        leftFileName: String(leftFile?.name || ""),
        rightFileName: String(rightFile?.name || ""),
        status: "failed",
        error: detail,
        matches: 0,
        exceptions: 0,
        matchPct: 0,
        discrepancyCount: 0,
        mappingIssueCount: 0,
        durationMs: Math.max(Date.now() - runStartedAt, 0),
        inputSnapshot
      });
    } finally {
      setReconcileLoading(false);
    }
  }

  async function handleRunSecondPass() {
    const jobId = String(reconResult?.job_id || "").trim();
    if (!jobId) {
      showToast(t("Second-pass failed: {error}", { error: "Missing job id" }), "error");
      return;
    }

    setSecondPassLoading(true);
    addLog(t("Running second-pass LLM on unmatched exceptions..."), "info");

    try {
      const response = await runSecondPass(jobId);
      const resultsPayload = response?.results && typeof response.results === "object"
        ? response.results
        : {};
      const normalizedResultsPayload = normalizeReconciliationResult(resultsPayload);

      const updatedResult = {
        ...normalizeReconciliationResult(reconResult || {}),
        ...normalizedResultsPayload,
        second_pass_stats:
          response?.second_pass_stats || normalizedResultsPayload?.metrics?.second_pass_stats || null
      };

      setReconResult(updatedResult);

      const additionalMatches = Number(
        response?.second_pass_stats?.second_pass_matches || 0
      );
      addLog(
        t("Second-pass completed: {count} additional matches", {
          count: formatNumber(additionalMatches)
        }),
        additionalMatches > 0 ? "success" : "info"
      );

      showToast(
        t("Second-pass completed: {count} additional matches", {
          count: formatNumber(additionalMatches)
        }),
        additionalMatches > 0 ? "success" : "info"
      );
    } catch (error) {
      const detail = error?.message || "Unknown error";
      addLog(t("Second-pass failed: {error}", { error: detail }), "error");
      showToast(t("Second-pass failed: {error}", { error: detail }), "error");
    } finally {
      setSecondPassLoading(false);
    }
  }

  async function handleLoadRunFromHistory(entry) {
    if (!entry || typeof entry !== "object") {
      return;
    }

    const hasActiveState = Boolean(
      leftFile ||
      rightFile ||
      reconResult ||
      mappingData ||
      toDisplayArray(mappingRows).length
    );
    if (hasActiveState) {
      const shouldReplace = window.confirm(
        t("Load this run and replace the current workspace state?")
      );
      if (!shouldReplace) {
        return;
      }
    }

    const entryId = String(entry.id || "");
    const snapshot =
      entry.inputSnapshot && typeof entry.inputSnapshot === "object"
        ? entry.inputSnapshot
        : null;
    const storedResultSnapshot =
      entry.resultSnapshot && typeof entry.resultSnapshot === "object"
        ? entry.resultSnapshot
        : null;

    setHistoryLoadingId(entryId);

    try {
      setLeftFile(null);
      setRightFile(null);

      const scenarioValue = String(
        snapshot?.scenarioType || entry.scenarioType || scenarioType
      ).trim();
      if (scenarioValue) {
        setScenarioType(scenarioValue);
      }

      setCreatedBy(
        normalizeTextInput(
          snapshot?.createdBy || entry.analyst,
          "analyst"
        )
      );
      setLeftLabel(
        normalizeTextInput(
          snapshot?.leftLabel || entry.leftSource,
          "Left Source"
        )
      );
      setRightLabel(
        normalizeTextInput(
          snapshot?.rightLabel || entry.rightSource,
          "Right Source"
        )
      );

      const replayMappingRows = prepareMappingRows(snapshot?.mappingRows);
      setMappingRows(replayMappingRows);
      setMappingData(buildReplayMappingData(snapshot));

      const jobId = String(entry.jobId || storedResultSnapshot?.job_id || "").trim();
      let replayResult = storedResultSnapshot
        ? normalizeReconciliationResult(storedResultSnapshot)
        : null;

      if (jobId) {
        try {
          const liveResponse = await getJobResults(jobId);
          const liveResult = normalizeReconciliationResult(liveResponse);
          replayResult = normalizeReconciliationResult({
            ...(replayResult || {}),
            ...liveResult,
            mapping_issues: toDisplayArray(liveResult.mapping_issues).length
              ? liveResult.mapping_issues
              : toDisplayArray(replayResult?.mapping_issues),
            discrepancies: toDisplayArray(liveResult.discrepancies).length
              ? liveResult.discrepancies
              : toDisplayArray(replayResult?.discrepancies),
            classified_exceptions: toDisplayArray(liveResult.classified_exceptions).length
              ? liveResult.classified_exceptions
              : toDisplayArray(replayResult?.classified_exceptions),
            journal_entries: toDisplayArray(liveResult.journal_entries).length
              ? liveResult.journal_entries
              : toDisplayArray(replayResult?.journal_entries),
            reconciliation_summary:
              liveResult.reconciliation_summary ||
              replayResult?.reconciliation_summary ||
              null,
            left_file: liveResult?.left_file || replayResult?.left_file || null,
            right_file: liveResult?.right_file || replayResult?.right_file || null
          });
        } catch (error) {
          const detail = error?.message || "Unknown error";
          addLog(
            t(
              "History replay used local snapshot because live results failed: {error}",
              { error: detail }
            ),
            "warning"
          );
          if (!replayResult) {
            showToast(t("Unable to load this run: {error}", { error: detail }), "error");
            return;
          }
        }
      }

      if (!replayResult) {
        showToast(t("This history entry does not have replayable details yet"), "error");
        return;
      }

      setReconResult(replayResult);
      setSelectedDiscrepancyId(String(replayResult.discrepancies?.[0]?.match_id || ""));
      setShowHistory(false);
      setCurrentPage(PAGE_SUMMARY);

      const loadedAt = new Date(entry.timestamp || Date.now()).toLocaleString(locale, {
        dateStyle: "medium",
        timeStyle: "short"
      });
      addLog(t("Loaded historical run from {time}", { time: loadedAt }), "success");
      showToast(t("Historical run loaded successfully"), "success");
    } finally {
      setHistoryLoadingId("");
    }
  }

  function handleExportResultsCsv() {
    if (!reconResult) {
      showToast(t("No reconciliation results available to export"), "error");
      return;
    }

    try {
      const rows = buildResultExportRows(reconResult, { leftLabel, rightLabel });
      const csvText = rowsToCsv(rows);
      const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
      const safeScenario = String(scenarioType || "reconciliation").replace(/[^a-z0-9_-]/gi, "_");
      const fileName = `${safeScenario}_results_${timestamp}.csv`;

      triggerCsvDownload(fileName, csvText);
      addLog(t("Results exported to {file}", { file: fileName }), "success");
      showToast(t("Results exported to {file}", { file: fileName }), "success");
    } catch (error) {
      const detail = error?.message || "Unknown error";
      addLog(t("Export failed: {error}", { error: detail }), "error");
      showToast(t("Export failed: {error}", { error: detail }), "error");
    }
  }

  const discrepancyList = toDisplayArray(reconResult?.discrepancies);
  const discrepancyByMatchId = useMemo(() => {
    return new Map(
      discrepancyList
        .filter((item) => item?.match_id !== undefined && item?.match_id !== null)
        .map((item) => [String(item.match_id), item])
    );
  }, [discrepancyList]);
  const selectedDiscrepancy =
    discrepancyByMatchId.get(String(selectedDiscrepancyId)) ||
    discrepancyList[0] ||
    null;

  const leftColumns = toDisplayArray(mappingData?.left?.columns);
  const rightColumns = toDisplayArray(mappingData?.right?.columns);
  const mappingIssues = toDisplayArray(reconResult?.mapping_issues);
  const matches = toDisplayArray(reconResult?.matches);
  const exceptions = toDisplayArray(reconResult?.exceptions);
  const classifiedExceptions = toDisplayArray(reconResult?.classified_exceptions);
  const journalEntries = toDisplayArray(reconResult?.journal_entries);
  const reconciliationSummary =
    reconResult?.reconciliation_summary && typeof reconResult.reconciliation_summary === "object"
      ? reconResult.reconciliation_summary
      : null;
  const bankAdjustments = toDisplayArray(reconciliationSummary?.bank_statement?.adjustments);
  const cashAdjustments = toDisplayArray(reconciliationSummary?.cash_book?.adjustments);
  const currentStageIndex = Math.max(STAGE_ORDER.indexOf(currentPage), 0);
  const onboardingHintByStage = {
    [PAGE_UPLOAD]: "Upload both sources, confirm labels, then run Analyze and Continue.",
    [PAGE_MAPPING]: "Accept high-confidence mappings first, then resolve only the conflicted fields.",
    [PAGE_SUMMARY]: "Review balances, exception buckets, and journal drafts before drilling into details.",
    [PAGE_RESULTS]: "Inspect discrepancies, clear exceptions, and export audit-ready outcomes."
  };
  const onboardingHint = onboardingHintByStage[currentPage] || onboardingHintByStage[PAGE_UPLOAD];
  const stageItems = [
    { key: PAGE_UPLOAD, label: t("Upload"), enabled: true },
    { key: PAGE_MAPPING, label: t("Mapping Diff"), enabled: Boolean(mappingData) },
    { key: PAGE_SUMMARY, label: t("Summary"), enabled: Boolean(reconResult) },
    { key: PAGE_RESULTS, label: t("Results"), enabled: Boolean(reconResult) }
  ];
  const scenarioLabelByValue = useMemo(() => {
    return Object.fromEntries(scenarioOptions.map((option) => [option.value, option.label]));
  }, []);

  return (
    <div className={`app-container archival-dashboard ${pageTransitioning ? "is-transitioning" : ""}`}>
      <header className="header archival-header">
        <div className="header-left archival-header-left">
          <div className="header-title archival-brand-block">
            <h1 className="archival-brand-title">
              <button
                type="button"
                className="archival-brand-link"
                onClick={onNavigateHome}
                aria-label="Return to homepage"
                title="Return to homepage"
              >
                The Archival Authority
              </button>
            </h1>
            <p>{t("AI-powered mapping and discrepancy review")}</p>
          </div>

          <nav className="archival-top-nav" aria-label={t("Workflow stages")}
          >
            {stageItems.map((stage, index) => (
              <button
                key={`top-stage-${stage.key}`}
                type="button"
                className={`archival-top-link ${currentPage === stage.key ? "active" : ""}`}
                onClick={() => goToPage(stage.key)}
                disabled={!stage.enabled}
              >
                {index + 1}. {stage.label}
              </button>
            ))}
          </nav>
        </div>

        <div className="header-right archival-header-right">
          <label className="locale-select" htmlFor="locale-select">
            <span className="material-symbols-outlined" aria-hidden="true">language</span>
            <span>{t("Language")}</span>
            <select
              id="locale-select"
              value={locale}
              onChange={(event) => setLocale(event.target.value)}
              aria-label={t("Language")}
            >
              {SUPPORTED_LOCALES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <button type="button" className="logs-btn" onClick={() => setShowLogs(true)}>
            <span className="material-symbols-outlined" aria-hidden="true">receipt_long</span>
            {t("Logs")} {logs.length > 0 && <span className="logs-count">{formatNumber(logs.length)}</span>}
          </button>

          <button
            type="button"
            className="logs-btn"
            onClick={() => {
              setShowLogs(false);
              setShowHistory(true);
            }}
          >
            <span className="material-symbols-outlined" aria-hidden="true">history</span>
            Run History
            {runHistory.length > 0 && <span className="logs-count">{formatNumber(runHistory.length)}</span>}
          </button>

          {!showOnboarding && (
            <button
              type="button"
              className="logs-btn archival-guide-btn"
              onClick={() => {
                localStorage.removeItem("recon-onboarding-dismissed");
                setShowOnboarding(true);
              }}
            >
              <span className="material-symbols-outlined" aria-hidden="true">school</span>
              Guide
            </button>
          )}

          <button
            type="button"
            className="theme-toggle"
            onClick={onToggleDarkMode}
            title={darkMode ? t("Switch to Light Mode") : t("Switch to Dark Mode")}
            aria-label={darkMode ? t("Switch to Light Mode") : t("Switch to Dark Mode")}
          >
            <span className="material-symbols-outlined" aria-hidden="true">
              {darkMode ? "light_mode" : "dark_mode"}
            </span>
          </button>

          <div className={`health-pill ${connection.ok ? "online" : "offline"}`}>{connectionLabel}</div>
        </div>
      </header>

      <div className="archival-layout">
        <aside className="archival-sidebar" aria-label="System navigation">
          <div className="archival-sidebar-head">
            <div className="archival-sidebar-title-wrap">
              <span className="material-symbols-outlined" aria-hidden="true">account_balance</span>
              <h2>System Ledger</h2>
            </div>
            <div className="archival-sidebar-pill">{connectionLabel}</div>
          </div>

          <div className="archival-sidebar-group">
            <p>Main Console</p>
            <button type="button" className="archival-side-link" onClick={() => goToPage(PAGE_UPLOAD)}>
              <span className="material-symbols-outlined" aria-hidden="true">sync_alt</span>
              Reconciliation
            </button>
            <button type="button" className="archival-side-link" onClick={() => setShowLogs(true)}>
              <span className="material-symbols-outlined" aria-hidden="true">history_edu</span>
              Audit Trails
            </button>
            <button
              type="button"
              className="archival-side-link"
              onClick={() => {
                setShowLogs(false);
                setShowHistory(true);
              }}
            >
              <span className="material-symbols-outlined" aria-hidden="true">schedule</span>
              Run History
            </button>
          </div>

          <button type="button" className="btn btn-primary archival-sidebar-action" onClick={() => goToPage(PAGE_UPLOAD)}>
            New Reconciliation
            <span className="material-symbols-outlined" aria-hidden="true">add</span>
          </button>
        </aside>

        <main className="main-shell arch-main-shell">
          <nav className="stage-nav arch-stage-nav" aria-label={t("Workflow stages")}
          >
            <div
              className="arch-stage-progress"
              style={{ "--arch-progress": `${((currentStageIndex + 1) / STAGE_ORDER.length) * 100}%` }}
              aria-hidden="true"
            />
            {stageItems.map((stage, index) => {
              const status = index < currentStageIndex ? "completed" : index === currentStageIndex ? "active" : "pending";
              const statusLabel = status === "active" ? "Active" : status === "completed" ? "Completed" : "Pending";

              return (
                <button
                  key={`stage-${stage.key}`}
                  type="button"
                  className={`stage-btn arch-stage-btn ${status} ${currentPage === stage.key ? "active" : ""}`}
                  onClick={() => goToPage(stage.key)}
                  disabled={!stage.enabled}
                >
                  <span className="arch-stage-index">{index + 1}</span>
                  <span className="arch-stage-copy">
                    <small>{statusLabel}</small>
                    <strong>{stage.label}</strong>
                  </span>
                </button>
              );
            })}
          </nav>
          {showOnboarding && (
            <section className="arch-onboard-banner" aria-live="polite">
              <div className="arch-onboard-copy">
                <p className="arch-onboard-kicker">Quick onboarding · ~90 seconds</p>
                <h3>Move from uploaded files to reconciled outcomes with a smooth, guided flow.</h3>
                <p>{onboardingHint}</p>
              </div>
              <div className="arch-onboard-actions">
                <button type="button" className="btn btn-secondary" onClick={dismissOnboarding}>
                  I&apos;ll explore on my own
                </button>
                <button type="button" className="btn btn-primary" onClick={() => goToPage(PAGE_UPLOAD)}>
                  Start with Upload
                </button>
              </div>
            </section>
          )}

          {processingStep && (
            <div className="processing-banner" role="status" aria-live="polite">
              <span className="loading-spinner" />
              {processingStep}
            </div>
          )}

          <div key={currentPage} className="page-view arch-step-view">
          {currentPage === PAGE_UPLOAD && (
            <section className="card page-card">
              <div className="card-header">
                <div className="card-title">
                  <span className="card-title-icon">1</span>
                  <h2>{t("Upload Source Files")}</h2>
                </div>

                <div className="page-actions-inline">
                  <button
                    className="btn btn-primary"
                    type="button"
                    onClick={handleSuggestMapping}
                    disabled={suggestionLoading || !leftFile || !rightFile}
                  >
                    {suggestionLoading ? (
                      <>
                        <span className="loading-spinner" />
                        {processingStep || t("Processing...")}
                      </>
                    ) : (
                      t("Analyze and Continue")
                    )}
                  </button>
                </div>
              </div>

              <form onSubmit={handleSuggestMapping}>
                <div className="upload-grid">
                  <div className="form-group">
                    <label>{t("Scenario Type")}</label>
                    <select value={scenarioType} onChange={(event) => setScenarioType(event.target.value)}>
                      {scenarioOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="form-group">
                    <label>{t("Analyst Name")}</label>
                    <input
                      value={createdBy}
                      onChange={(event) => setCreatedBy(event.target.value)}
                      maxLength={64}
                      placeholder={t("Your name")}
                    />
                  </div>

                  <div className="form-group">
                    <label>{t("Left Source Label")}</label>
                    <input
                      value={leftLabel}
                      onChange={(event) => setLeftLabel(event.target.value)}
                      maxLength={64}
                      placeholder="e.g., Bank Statement"
                    />
                  </div>

                  <div className="form-group">
                    <label>{t("Right Source Label")}</label>
                    <input
                      value={rightLabel}
                      onChange={(event) => setRightLabel(event.target.value)}
                      maxLength={64}
                      placeholder="e.g., GL Records"
                    />
                  </div>
                </div>

                <div className="file-upload-area">
                  <label className={`file-box left ${leftFile ? "loaded" : ""}`}>
                    <input
                      type="file"
                      accept={ACCEPTED_FILE_EXTENSIONS.join(",")}
                      onChange={(event) => handleFileSelect("left", event)}
                      aria-label={leftLabel}
                    />
                    <div className="file-box-content">
                      <span className="file-box-icon">{leftFile ? "OK" : "L"}</span>
                      <span className="file-box-text" title={leftFile ? leftFile.name : leftLabel}>
                        {leftFile ? leftFile.name : leftLabel}
                      </span>
                      <span className="file-box-subtext">
                        {leftFile
                          ? `${formatFileSizeKb(leftFile, locale)} KB`
                          : t("Drop or click to upload")}
                      </span>
                    </div>
                  </label>

                  <label className={`file-box right ${rightFile ? "loaded" : ""}`}>
                    <input
                      type="file"
                      accept={ACCEPTED_FILE_EXTENSIONS.join(",")}
                      onChange={(event) => handleFileSelect("right", event)}
                      aria-label={rightLabel}
                    />
                    <div className="file-box-content">
                      <span className="file-box-icon">{rightFile ? "OK" : "R"}</span>
                      <span className="file-box-text" title={rightFile ? rightFile.name : rightLabel}>
                        {rightFile ? rightFile.name : rightLabel}
                      </span>
                      <span className="file-box-subtext">
                        {rightFile
                          ? `${formatFileSizeKb(rightFile, locale)} KB`
                          : t("Drop or click to upload")}
                      </span>
                    </div>
                  </label>
                </div>

                <div className="arch-upload-meta" aria-label="Automation summary">
                  <article>
                    <h4>Automated Mapping</h4>
                    <p>Neural Engine v4.2</p>
                    <small>System identifies schema and proposes field mapping immediately after upload.</small>
                  </article>
                  <article>
                    <h4>Validation Mode</h4>
                    <p>Strict Forensic</p>
                    <small>Audit trail generation and discrepancy categorization remain active across all steps.</small>
                  </article>
                  <article>
                    <h4>Estimated TTR</h4>
                    <p>&lt; 180 Seconds</p>
                    <small>Time to reconciliation adjusts based on active queue and source quality.</small>
                  </article>
                </div>
              </form>
            </section>
          )}

          {currentPage === PAGE_MAPPING && (
            <section className="page-stack">
              {mappingData ? (
                <>
                  <div className="card page-card">
                    <div className="card-header">
                      <div className="card-title">
                        <span className="card-title-icon">2</span>
                        <h2>{t("Column Mapping Diff")}</h2>
                      </div>
                      <div className="page-actions-inline">
                        <button className="btn btn-secondary" type="button" onClick={() => goToPage(PAGE_UPLOAD)}>
                          {t("Back to Upload")}
                        </button>
                        <button
                          className="btn btn-primary"
                          type="button"
                          onClick={handleRunReconciliation}
                          disabled={reconcileLoading}
                        >
                          {reconcileLoading ? (
                            <>
                              <span className="loading-spinner" />
                              {t("Processing...")}
                            </>
                          ) : (
                            t("Run Reconciliation")
                          )}
                        </button>
                      </div>
                    </div>

                    <div className="mapping-top-grid">
                      <div>{renderPreviewTable(mappingData.left, "left", { t, formatNumber })}</div>
                      <div>{renderPreviewTable(mappingData.right, "right", { t, formatNumber })}</div>
                    </div>
                  </div>

                  <div className="card page-card mapping-editor-card">
                    <div className="mapping-editor-header">
                      <h3>
                        <span className="llm-badge">AI</span>
                        {t("Merge Conflict Style Mapping")}
                      </h3>
                      <p>{t("Resolve each field by selecting the matching columns on both sides.")}</p>
                    </div>

                    <div className="merge-list">
                      {mappingRows.length ? (
                        mappingRows.map((row) => (
                          <article
                            key={row._rowKey}
                            className={`merge-card ${row.source === "manual" ? "manual" : "ai"}`}
                          >
                            <div className="merge-card-header">
                              <div className="merge-field-meta">
                                <code title={row.field}>{row.field}</code>
                                <strong title={row.label}>{row.label}</strong>
                                {row.required && <span className="required-tag">{t("Required")}</span>}
                              </div>
                              <div className="merge-field-score">
                                <span className="source-pill">
                                  {row.source === "manual" ? t("Manual") : "AI"}
                                </span>
                                <ConfidenceBar confidence={row.confidence || 0} />
                              </div>
                            </div>

                            {row.rationale && <p className="merge-rationale">{String(row.rationale)}</p>}

                            <div className="conflict-block">
                              <div className="conflict-marker left">&lt;&lt;&lt;&lt;&lt;&lt;&lt; {leftLabel}</div>
                              <div className="conflict-input left">
                                <label htmlFor={`${row._rowKey}-left`}>{t("Left Column")}</label>
                                <select
                                  id={`${row._rowKey}-left`}
                                  value={row.left_column || ""}
                                  onChange={(event) =>
                                    updateMapping(row._rowKey, "left_column", event.target.value)
                                  }
                                >
                                  <option value="">{t("-- Not mapped --")}</option>
                                  {leftColumns.map((column) => (
                                    <option key={`${row._rowKey}-left-${column}`} value={column}>
                                      {column}
                                    </option>
                                  ))}
                                </select>
                              </div>

                              <div className="conflict-marker middle">======= {t("Resolve Mapping")}</div>

                              <div className="conflict-input right">
                                <label htmlFor={`${row._rowKey}-right`}>{t("Right Column")}</label>
                                <select
                                  id={`${row._rowKey}-right`}
                                  value={row.right_column || ""}
                                  onChange={(event) =>
                                    updateMapping(row._rowKey, "right_column", event.target.value)
                                  }
                                >
                                  <option value="">{t("-- Not mapped --")}</option>
                                  {rightColumns.map((column) => (
                                    <option key={`${row._rowKey}-right-${column}`} value={column}>
                                      {column}
                                    </option>
                                  ))}
                                </select>
                              </div>

                              <div className="conflict-marker right">&gt;&gt;&gt;&gt;&gt;&gt;&gt; {rightLabel}</div>
                            </div>
                          </article>
                        ))
                      ) : (
                        <div className="empty-state">{t("No mapping suggestions were returned.")}</div>
                      )}
                    </div>
                  </div>
                </>
              ) : (
                <div className="card page-card">
                  <div className="empty-state">{t("Run mapping from the upload page first.")}</div>
                </div>
              )}
            </section>
          )}

          {currentPage === PAGE_SUMMARY && (
            <section className="results-section">
              {reconResult ? (
                <div className="card page-card">
                  <div className="card-header">
                    <div className="card-title">
                      <span className="card-title-icon">3</span>
                      <h2>{t("Summary Overview")}</h2>
                    </div>
                    <div className="header-actions">
                      <button className="btn btn-secondary" type="button" onClick={() => goToPage(PAGE_MAPPING)}>
                        {t("Back to Mapping")}
                      </button>
                      <button className="btn btn-secondary" type="button" onClick={handleExportResultsCsv}>
                        {t("Export Results CSV")}
                      </button>
                      <button className="btn btn-primary" type="button" onClick={() => goToPage(PAGE_RESULTS)}>
                        {t("View Detailed Results")}
                      </button>
                    </div>
                  </div>

                  <div className="metrics-grid">
                    <div className="metric-card">
                      <div className="metric-card-label">{t("Left Records")}</div>
                      <div className="metric-card-value">{formatNumber(reconResult.left_file?.valid_rows ?? 0)}</div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-card-label">{t("Right Records")}</div>
                      <div className="metric-card-value">{formatNumber(reconResult.right_file?.valid_rows ?? 0)}</div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-card-label">{t("Matches")}</div>
                      <div className="metric-card-value success">
                        {formatNumber(reconResult.metrics?.matched_count ?? 0)}
                      </div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-card-label">{t("Exceptions")}</div>
                      <div className="metric-card-value warning">
                        {formatNumber(reconResult.metrics?.exception_count ?? 0)}
                      </div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-card-label">{t("Match Rate")}</div>
                      <div className="metric-card-value">{formatPercent(reconResult.metrics?.matched_pct ?? 0)}</div>
                    </div>
                  </div>

                  {reconciliationSummary && (
                    <div className="table-container reconciliation-summary-container">
                      <div className="table-header">
                        <h3>{t("Reconciliation Summary")}</h3>
                      </div>
                      <div className="summary-balance-grid">
                        <div className="summary-balance-card">
                          <h4>{leftLabel || t("Bank Statement")}</h4>
                          <div className="summary-balance-row">
                            <span>{t("Unadjusted Closing Balance")}</span>
                            <strong>{formatAmount(reconciliationSummary.bank_statement?.unadjusted_closing_balance)}</strong>
                          </div>
                          <div className="summary-balance-row">
                            <span>{t("Adjusted Closing Balance")}</span>
                            <strong>{formatAmount(reconciliationSummary.bank_statement?.adjusted_closing_balance)}</strong>
                          </div>
                        </div>
                        <div className="summary-balance-card">
                          <h4>{rightLabel || t("Cash Book")}</h4>
                          <div className="summary-balance-row">
                            <span>{t("Unadjusted Closing Balance")}</span>
                            <strong>{formatAmount(reconciliationSummary.cash_book?.unadjusted_closing_balance)}</strong>
                          </div>
                          <div className="summary-balance-row">
                            <span>{t("Adjusted Closing Balance")}</span>
                            <strong>{formatAmount(reconciliationSummary.cash_book?.adjusted_closing_balance)}</strong>
                          </div>
                        </div>
                        <div className="summary-balance-card unreconciled-card">
                          <h4>{t("Unreconciled Amount")}</h4>
                          <div className="summary-balance-row">
                            <strong>{formatAmount(reconciliationSummary.unreconciled_amount)}</strong>
                          </div>
                          <small>{t("Absolute difference between adjusted balances")}</small>
                        </div>
                      </div>

                      <div className="summary-adjustments-grid">
                        <div className="summary-adjustments-panel">
                          <h4>{t("Bank Statement Adjustments")}</h4>
                          <ul>
                            {bankAdjustments.map((item) => (
                              <li key={`bank-adjustment-${item.bucket_key}`}>
                                <span>{String(item.label || item.bucket_key)}</span>
                                <span>
                                  {String(item.operation || "none").toUpperCase()} | {formatAmount(item.amount)}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div className="summary-adjustments-panel">
                          <h4>{t("Cash Book Adjustments")}</h4>
                          <ul>
                            {cashAdjustments.map((item) => (
                              <li key={`cash-adjustment-${item.bucket_key}`}>
                                <span>{String(item.label || item.bucket_key)}</span>
                                <span>
                                  {String(item.operation || "none").toUpperCase()} | {formatAmount(item.amount)}
                                </span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="table-container">
                    <div className="table-header">
                      <h3>{t("Classified Exceptions")}</h3>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>{t("Exception ID")}</th>
                            <th>{t("Transaction")}</th>
                            <th>{t("Bucket")}</th>
                            <th>{t("Operation")}</th>
                            <th>{t("Amount")}</th>
                            <th>{t("Confidence")}</th>
                            <th>{t("Rationale")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {classifiedExceptions.length ? (
                            classifiedExceptions.map((entry, index) => (
                              <tr key={String(entry.exception_id || `classified-${index + 1}`)}>
                                <td className="cell-ellipsis" title={String(entry.exception_id || "")}> {
                                  String(entry.exception_id || "")
                                }</td>
                                <td className="cell-ellipsis" title={String(entry.transaction_id || "")}> {
                                  String(entry.transaction_id || "")
                                }</td>
                                <td className="cell-ellipsis" title={String(entry.bucket_label || entry.bucket_key || "")}> {
                                  String(entry.bucket_label || entry.bucket_key || "")
                                }</td>
                                <td>{String(entry.operation || "none")}</td>
                                <td>{formatAmount(entry.amount)}</td>
                                <td>{formatPercent(Number(entry.confidence || 0) * 100)}</td>
                                <td className="cell-ellipsis" title={String(entry.rationale || "")}> {
                                  String(entry.rationale || "")
                                }</td>
                              </tr>
                            ))
                          ) : (
                            <tr>
                              <td colSpan={7} className="empty-state">
                                {t("No classified exceptions available")}
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="table-container">
                    <div className="table-header">
                      <h3>{t("Journal Entries")}</h3>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>{t("Entry ID")}</th>
                            <th>{t("Date")}</th>
                            <th>{t("Debit")}</th>
                            <th>{t("Credit")}</th>
                            <th>{t("Amount")}</th>
                            <th>{t("Narration")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {journalEntries.length ? (
                            journalEntries.map((entry, index) => (
                              <tr key={String(entry.entry_id || `journal-${index + 1}`)}>
                                <td>{String(entry.entry_id || "")}</td>
                                <td>{String(entry.entry_date || "")}</td>
                                <td className="cell-ellipsis" title={String(entry.debit_account || "")}> {
                                  String(entry.debit_account || "")
                                }</td>
                                <td className="cell-ellipsis" title={String(entry.credit_account || "")}> {
                                  String(entry.credit_account || "")
                                }</td>
                                <td>{formatAmount(entry.amount)}</td>
                                <td className="cell-ellipsis" title={String(entry.narration || "")}> {
                                  String(entry.narration || "")
                                }</td>
                              </tr>
                            ))
                          ) : (
                            <tr>
                              <td colSpan={6} className="empty-state">
                                {t("No journal entries generated")}
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="card page-card">
                  <div className="empty-state">{t("Run reconciliation from the mapping page first.")}</div>
                </div>
              )}
            </section>
          )}

          {currentPage === PAGE_RESULTS && (
            <section className="results-section">
              {reconResult ? (
                <div className="card page-card">
                  <div className="card-header">
                    <div className="card-title">
                      <span className="card-title-icon">4</span>
                      <h2>{t("Reconciliation Results")}</h2>
                    </div>
                    <div className="header-actions">
                      <button
                        className="btn btn-primary"
                        type="button"
                        onClick={handleRunSecondPass}
                        disabled={
                          secondPassLoading ||
                          reconcileLoading ||
                          Number(reconResult.metrics?.exception_count || 0) <= 0
                        }
                      >
                        {secondPassLoading
                          ? `${t("Retry Unmatched with LLM")}...`
                          : t("Retry Unmatched with LLM")}
                      </button>
                      <button className="btn btn-secondary" type="button" onClick={handleExportResultsCsv}>
                        {t("Export Results CSV")}
                      </button>
                      <button className="btn btn-secondary" type="button" onClick={() => goToPage(PAGE_SUMMARY)}>
                        {t("Back to Summary")}
                      </button>
                      <button className="btn btn-secondary" type="button" onClick={() => goToPage(PAGE_MAPPING)}>
                        {t("Back to Mapping")}
                      </button>
                    </div>
                  </div>

                  {mappingIssues.length > 0 && (
                    <div className="issues-banner">
                      <h3>{t("Mapping Issues Detected")}</h3>
                      <ul>
                        {mappingIssues.map((issue, index) => (
                          <li key={`mapping-issue-${index}`}>
                            {issue.side ? `${String(issue.side).toUpperCase()} | ` : ""}
                            {issue.field ? `${issue.field}: ` : ""}
                            {issue.message}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="metrics-grid">
                    <div className="metric-card">
                      <div className="metric-card-label">{t("Left Records")}</div>
                      <div className="metric-card-value">{formatNumber(reconResult.left_file?.valid_rows ?? 0)}</div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-card-label">{t("Right Records")}</div>
                      <div className="metric-card-value">{formatNumber(reconResult.right_file?.valid_rows ?? 0)}</div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-card-label">{t("Matches")}</div>
                      <div className="metric-card-value success">
                        {formatNumber(reconResult.metrics?.matched_count ?? 0)}
                      </div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-card-label">{t("Exceptions")}</div>
                      <div className="metric-card-value warning">
                        {formatNumber(reconResult.metrics?.exception_count ?? 0)}
                      </div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-card-label">{t("Match Rate")}</div>
                      <div className="metric-card-value">{formatPercent(reconResult.metrics?.matched_pct ?? 0)}</div>
                    </div>
                  </div>

                  <div className="table-container">
                    <div className="table-header">
                      <h3>{t("Matched Transactions")}</h3>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>{t("Match ID")}</th>
                            <th>{t("Left")}</th>
                            <th>{t("Right")}</th>
                            <th>{t("Amount Delta")}</th>
                            <th>{t("Date Delta")}</th>
                            <th>{t("Algorithm")}</th>
                            <th>{t("Status")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {matches.length ? (
                            matches.map((match, index) => {
                              const matchId = String(match?.id || `match-${index + 1}`);
                              const discrepancy = discrepancyByMatchId.get(matchId);
                              const issueCount = toDisplayArray(discrepancy?.issues).length;

                              return (
                                <tr key={matchId}>
                                  <td className="cell-ellipsis" title={matchId}>
                                    <strong>{matchId}</strong>
                                  </td>
                                  <td className="cell-ellipsis" title={String(match?.left?.id || match?.a || "")}>{
                                    String(match?.left?.id || match?.a || "")
                                  }</td>
                                  <td className="cell-ellipsis" title={String(match?.right?.id || match?.b || "")}>{
                                    String(match?.right?.id || match?.b || "")
                                  }</td>
                                  <td className="cell-ellipsis" title={String(match?.amount_delta || "0.00")}>{
                                    String(match?.amount_delta || "0.00")
                                  }</td>
                                  <td>{String(match?.date_delta_days ?? 0)}d</td>
                                  <td className="cell-ellipsis" title={String(match?.algo || "")}>{
                                    String(match?.algo || "")
                                  }</td>
                                  <td>
                                    <button
                                      type="button"
                                      className={`discrepancy-btn ${issueCount > 0 ? "alert" : "aligned"}`}
                                      onClick={() => setSelectedDiscrepancyId(matchId)}
                                    >
                                      {issueCount > 0
                                        ? `${formatNumber(issueCount)} ${t("issue(s)")}`
                                        : t("Aligned")}
                                    </button>
                                  </td>
                                </tr>
                              );
                            })
                          ) : (
                            <tr>
                              <td colSpan={7} className="empty-state">
                                {t("No matches found")}
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="diff-workbench">
                    <div className="diff-list">
                      <div className="diff-list-header">
                        <h3>{t("Discrepancy Inspector")}</h3>
                      </div>
                      <ul>
                        {discrepancyList.length ? (
                          discrepancyList.map((item, index) => {
                            const matchId = String(item?.match_id || `discrepancy-${index + 1}`);
                            const issueCount = toDisplayArray(item?.issues).length;

                            return (
                              <li key={matchId}>
                                <button
                                  type="button"
                                  className={
                                    String(selectedDiscrepancy?.match_id || "") === matchId ? "active" : ""
                                  }
                                  onClick={() => setSelectedDiscrepancyId(matchId)}
                                >
                                  <span>{matchId}</span>
                                  <small>
                                    {issueCount ? `${formatNumber(issueCount)} ${t("diffs")}` : t("Aligned")}
                                  </small>
                                </button>
                              </li>
                            );
                          })
                        ) : (
                          <div className="empty-state compact">{t("All matched pairs are aligned.")}</div>
                        )}
                      </ul>
                    </div>

                    <div className="diff-detail">
                      {selectedDiscrepancy ? (
                        <>
                          <div className="diff-detail-header">
                            <h3>{t("Match Details: {id}", { id: selectedDiscrepancy.match_id })}</h3>
                            <p>{t("Side-by-side snapshot comparison")}</p>
                          </div>

                          <div className="diff-columns">
                            <div className="diff-side left">
                              <div className="diff-side-header" title={leftLabel}>
                                {leftLabel}
                              </div>
                              <pre>{JSON.stringify(selectedDiscrepancy.left_snapshot || {}, null, 2)}</pre>
                            </div>
                            <div className="diff-side right">
                              <div className="diff-side-header" title={rightLabel}>
                                {rightLabel}
                              </div>
                              <pre>{JSON.stringify(selectedDiscrepancy.right_snapshot || {}, null, 2)}</pre>
                            </div>
                          </div>

                          <div className="issue-list">
                            <h4>{t("Detected Discrepancies")}</h4>
                            {toDisplayArray(selectedDiscrepancy.issues).length ? (
                              <ul>
                                {selectedDiscrepancy.issues.map((issue, index) => (
                                  <li key={`issue-${index}`} className={issue.severity || "medium"}>
                                    <strong>{issue.field}</strong>: {issue.note}
                                    <br />
                                    <span className="issue-values">
                                      {String(issue.left ?? "")} vs {String(issue.right ?? "")}
                                    </span>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="aligned-note">{t("No discrepancies found for this match.")}</p>
                            )}
                          </div>
                        </>
                      ) : (
                        <div className="empty-state">
                          <p>{t("Select a matched pair to inspect differences.")}</p>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="table-container">
                    <div className="table-header">
                      <h3>{t("Unmatched / Exception Transactions")}</h3>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>{t("ID")}</th>
                            <th>{t("Transaction")}</th>
                            <th>{t("Status")}</th>
                            <th>{t("Reason")}</th>
                            <th>{t("Recommended Action")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {exceptions.length ? (
                            exceptions.map((exception, index) => {
                              const exceptionId = String(exception?.id || `exception-${index + 1}`);
                              const transactionValue = String(
                                exception?.transaction?.transaction_id || exception?.txn || ""
                              );

                              return (
                                <tr key={exceptionId}>
                                  <td className="cell-ellipsis" title={exceptionId}>
                                    <strong>{exceptionId}</strong>
                                  </td>
                                  <td className="cell-ellipsis" title={transactionValue}>{transactionValue}</td>
                                  <td>
                                    <span
                                      className={`discrepancy-btn ${
                                        exception.status === "no_candidate" ? "alert" : ""
                                      }`}
                                    >
                                      {String(exception.status || "")}
                                    </span>
                                  </td>
                                  <td className="cell-ellipsis" title={String(exception.reason || "")}>
                                    {String(exception.reason || "")}
                                  </td>
                                  <td
                                    className="cell-ellipsis"
                                    title={String(
                                      exception.recommended_action || t("Review source data and mapping")
                                    )}
                                  >
                                    {String(
                                      exception.recommended_action || t("Review source data and mapping")
                                    )}
                                  </td>
                                </tr>
                              );
                            })
                          ) : (
                            <tr>
                              <td colSpan={5} className="empty-state">
                                {t("No exceptions. All transactions matched.")}
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="card page-card">
                  <div className="empty-state">{t("Run reconciliation from the mapping page first.")}</div>
                </div>
              )}
            </section>
          )}
        </div>
      </main>
      </div>

      {showLogs && (
        <div className="logs-overlay" onClick={() => setShowLogs(false)}>
          <div
            className="logs-modal"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label={t("Process Logs")}
          >
            <div className="logs-header">
              <h3>{t("Process Logs")}</h3>
              <button type="button" className="logs-close" onClick={() => setShowLogs(false)}>
                x
              </button>
            </div>
            <div className="logs-content">
              {logs.length === 0 ? (
                <div className="logs-empty">{t("No logs yet. Run a process to see logs.")}</div>
              ) : (
                logs.map((log, index) => (
                  <div key={`log-${index}`} className={`log-entry log-${log.type}`}>
                    <span className="log-time">{log.timestamp}</span>
                    <span className="log-message" title={log.message}>
                      {log.message}
                    </span>
                  </div>
                ))
              )}
            </div>
            <div className="logs-footer">
              <button type="button" className="btn btn-secondary" onClick={clearLogs}>
                {t("Clear Logs")}
              </button>
              <button type="button" className="btn btn-primary" onClick={() => setShowLogs(false)}>
                {t("Close")}
              </button>
            </div>
          </div>
        </div>
      )}

      {showHistory && (
        <div className="logs-overlay" onClick={() => setShowHistory(false)}>
          <div
            className="logs-modal history-modal"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Run History"
          >
            <div className="logs-header">
              <h3>Run History</h3>
              <button type="button" className="logs-close" onClick={() => setShowHistory(false)}>
                x
              </button>
            </div>

            <div className="logs-content history-content">
              {runHistory.length === 0 ? (
                <div className="logs-empty">No previous runs yet. Complete reconciliation once to start history.</div>
              ) : (
                <div className="history-table-wrap">
                  <table className="history-table">
                    <thead>
                      <tr>
                        <th>Run Time</th>
                        <th>Scenario</th>
                        <th>Sources</th>
                        <th>Status</th>
                        <th>Matches</th>
                        <th>Exceptions</th>
                        <th>Match Rate</th>
                        <th>Duration</th>
                        <th>{t("Action")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {runHistory.map((entry) => {
                        const timeLabel = new Date(entry.timestamp).toLocaleString(locale, {
                          dateStyle: "medium",
                          timeStyle: "short"
                        });
                        const isLoading = historyLoadingId === String(entry.id || "");
                        const canLoadEntry = Boolean(entry.jobId || entry.resultSnapshot);

                        return (
                          <tr key={entry.id}>
                            <td className="cell-ellipsis" title={timeLabel}>{timeLabel}</td>
                            <td className="cell-ellipsis" title={scenarioLabelByValue[entry.scenarioType] || entry.scenarioType}>
                              {scenarioLabelByValue[entry.scenarioType] || entry.scenarioType}
                            </td>
                            <td className="cell-ellipsis" title={`${entry.leftSource} vs ${entry.rightSource}`}>
                              {entry.leftSource} vs {entry.rightSource}
                            </td>
                            <td>
                              <span className={`history-status history-${entry.status}`}>
                                {entry.status === "completed"
                                  ? "Completed"
                                  : entry.status === "mapping_failed"
                                    ? "Mapping Failed"
                                    : "Failed"}
                              </span>
                            </td>
                            <td>{formatNumber(entry.matches || 0)}</td>
                            <td>{formatNumber(entry.exceptions || 0)}</td>
                            <td>{formatPercent(entry.matchPct || 0)}</td>
                            <td>{decimalFormatter.format(Number(entry.durationMs || 0) / 1000)}s</td>
                            <td className="history-action-cell">
                              <button
                                type="button"
                                className="btn btn-secondary history-load-btn"
                                title={t("Load this run into workspace")}
                                onClick={() => handleLoadRunFromHistory(entry)}
                                disabled={Boolean(historyLoadingId) || !canLoadEntry}
                              >
                                {isLoading ? t("Loading...") : t("Load")}
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="logs-footer">
              <button type="button" className="btn btn-secondary" onClick={clearRunHistory}>
                Clear History
              </button>
              <button type="button" className="btn btn-primary" onClick={() => setShowHistory(false)}>
                {t("Close")}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className={`toast ${toast.message ? "show" : ""} ${toast.kind}`} role="status" aria-live="polite">
        {toast.message}
      </div>
    </div>
  );
}
