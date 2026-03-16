const JSON_HEADERS = {
  "Content-Type": "application/json"
};

export async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers:
      options.body instanceof FormData
        ? options.headers
        : {
            ...JSON_HEADERS,
            ...(options.headers || {})
          }
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;

    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch (_error) {
      const text = await response.text();
      if (text) {
        detail = text;
      }
    }

    throw new Error(detail);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
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
