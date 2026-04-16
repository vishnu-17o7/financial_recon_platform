const JSON_HEADERS = {
  "Content-Type": "application/json"
};

const DEFAULT_TIMEOUT_MS = 60000;
const MAPPING_SUGGEST_TIMEOUT_MS = 120000;
const RECONCILIATION_TIMEOUT_MS = 300000;
const JOB_RUN_TIMEOUT_MS = 180000;

function getRequestTimeout(path, timeoutMs) {
  if (typeof timeoutMs === "number" && Number.isFinite(timeoutMs) && timeoutMs > 0) {
    return timeoutMs;
  }

  if (typeof path === "string" && path.includes("/ingestion/mapping/suggest")) {
    return MAPPING_SUGGEST_TIMEOUT_MS;
  }

  if (typeof path === "string" && path.includes("/ingestion/mapping/reconcile")) {
    return RECONCILIATION_TIMEOUT_MS;
  }

  if (
    typeof path === "string" &&
    path.includes("/reconciliation/jobs/") &&
    (path.endsWith("/run") || path.endsWith("/run_second_pass"))
  ) {
    return JOB_RUN_TIMEOUT_MS;
  }

  return DEFAULT_TIMEOUT_MS;
}

async function getErrorDetail(response) {
  const fallback = `${response.status} ${response.statusText}`.trim();

  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string" && payload.detail.trim()) {
      return payload.detail;
    }
    if (payload && typeof payload === "object") {
      return JSON.stringify(payload);
    }
  } catch (_error) {
    // Ignore JSON parse errors and try plain text payload.
  }

  try {
    const text = await response.text();
    if (typeof text === "string" && text.trim()) {
      return text;
    }
  } catch (_error) {
    // Ignore text parse errors and use fallback.
  }

  return fallback || "Request failed";
}

export async function apiRequest(path, options = {}) {
  const controller = new AbortController();
  const timeoutMs = getRequestTimeout(path, options.timeoutMs);
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  let response;

  try {
    response = await fetch(path, {
      ...options,
      signal: controller.signal,
      headers:
        options.body instanceof FormData
          ? options.headers
          : {
              ...JSON_HEADERS,
              ...(options.headers || {})
            }
    });
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
    }

    throw new Error("Unable to reach the server. Check your network connection and try again.");
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    const detail = await getErrorDetail(response);
    throw new Error(detail);
  }

  if (response.status === 204) {
    return null;
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }

  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch (_error) {
    return text;
  }
}

export function checkHealth() {
  return apiRequest("/health");
}

export function uploadAndIngest({ parserKey, scenarioType, file }) {
  const formData = new FormData();
  formData.append("parser_key", parserKey);
  formData.append("scenario_type", scenarioType);
  formData.append("file", file);

  return apiRequest("/ingestion/upload", {
    method: "POST",
    body: formData
  });
}

export function suggestColumnMapping({ scenarioType, leftFile, rightFile }) {
  const formData = new FormData();
  formData.append("scenario_type", scenarioType);
  formData.append("left_file", leftFile);
  formData.append("right_file", rightFile);

  return apiRequest("/ingestion/mapping/suggest", {
    method: "POST",
    body: formData
  });
}

export function reconcileWithMapping({
  scenarioType,
  createdBy,
  leftLabel,
  rightLabel,
  leftFile,
  rightFile,
  mapping
}) {
  const formData = new FormData();
  formData.append("scenario_type", scenarioType);
  formData.append("created_by", createdBy || "ui-analyst");
  formData.append("left_label", leftLabel || "Left Source");
  formData.append("right_label", rightLabel || "Right Source");
  formData.append("mapping_json", JSON.stringify(mapping));
  formData.append("left_file", leftFile);
  formData.append("right_file", rightFile);

  return apiRequest("/ingestion/mapping/reconcile", {
    method: "POST",
    body: formData
  });
}

export function createJob(payload) {
  return apiRequest("/reconciliation/jobs", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function runJob(jobId) {
  return apiRequest(`/reconciliation/jobs/${encodeURIComponent(jobId)}/run`, {
    method: "POST"
  });
}

export function runSecondPass(jobId) {
  return apiRequest(`/reconciliation/jobs/${encodeURIComponent(jobId)}/run_second_pass`, {
    method: "POST"
  });
}

export function getJobResults(jobId) {
  return apiRequest(`/reconciliation/jobs/${encodeURIComponent(jobId)}/results`);
}

export function explainMatch({ transactionId, matchId }) {
  return apiRequest("/reconciliation/explain_match", {
    method: "POST",
    body: JSON.stringify({
      transaction_id: transactionId,
      match_id: matchId
    })
  });
}

export function explainException({ transactionId, exceptionId }) {
  return apiRequest("/reconciliation/explain_exception", {
    method: "POST",
    body: JSON.stringify({
      transaction_id: transactionId,
      exception_id: exceptionId
    })
  });
}

export function overrideMatch({ matchId, autoAccepted, reason, actor }) {
  return apiRequest("/reconciliation/matches/override", {
    method: "POST",
    body: JSON.stringify({
      match_id: matchId,
      auto_accepted: autoAccepted,
      reason,
      actor
    })
  });
}
