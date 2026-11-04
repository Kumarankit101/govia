const byId = (id) => document.getElementById(id);

function setState(element, kind, title, message) {
  const icons = { loading: "↻", empty: "↗", error: "!" };
  element.className = `state-card ${kind === "error" ? "error-state" : kind === "loading" ? "loading" : "empty-state"}`;
  element.innerHTML = "";
  const icon = document.createElement("span");
  icon.className = "state-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = icons[kind] || "·";
  const copy = document.createElement("div");
  const strong = document.createElement("strong");
  strong.textContent = title;
  const paragraph = document.createElement("p");
  paragraph.textContent = message;
  copy.append(strong, paragraph);
  element.append(icon, copy);
  element.hidden = false;
}

function messageFrom(error) {
  const body = error.body;
  if (!body?.error) return error.message || "The request failed";
  const details = body.error.details;
  if (Array.isArray(details) && details.length) {
    return `${body.error.message}: ${details.map((item) => `${item.field} ${item.message}`).join("; ")}`;
  }
  return body.error.message;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  let body;
  try { body = await response.json(); } catch { body = null; }
  if (!response.ok) {
    const error = new Error(`Request failed (${response.status})`);
    error.body = body;
    throw error;
  }
  return { body, status: response.status };
}

async function checkHealth() {
  try {
    await api("/health");
    byId("health-dot").className = "status-dot ok";
    byId("health-text").textContent = "Local service online";
  } catch {
    byId("health-dot").className = "status-dot error";
    byId("health-text").textContent = "Service unavailable";
  }
}

function activateTab(selected) {
  const observationSelected = selected === "observation";
  byId("observation-tab").classList.toggle("active", observationSelected);
  byId("mapping-tab").classList.toggle("active", !observationSelected);
  byId("observation-tab").setAttribute("aria-selected", String(observationSelected));
  byId("mapping-tab").setAttribute("aria-selected", String(!observationSelected));
  byId("observation-panel").hidden = !observationSelected;
  byId("mapping-panel").hidden = observationSelected;
}

async function submitJson(event, endpoint, inputId, statusId, noun) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type='submit']");
  const status = byId(statusId);
  status.className = "form-status";
  status.textContent = "Submitting…";
  button.disabled = true;
  try {
    JSON.parse(byId(inputId).value);
    const result = await api(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: byId(inputId).value,
    });
    const wasCreated = result.status === 201;
    status.className = "form-status success";
    status.textContent = wasCreated ? `${noun} stored successfully.` : `Identical retry accepted; no duplicate created.`;
  } catch (error) {
    status.className = "form-status error";
    status.textContent = error instanceof SyntaxError ? `Invalid JSON: ${error.message}` : messageFrom(error);
  } finally {
    button.disabled = false;
  }
}

function formatCoordinate(value) {
  return typeof value === "number" ? value.toFixed(4).replace(/\.?0+$/, "") : value;
}

async function inspectObservation(observationId, knownItem = null) {
  const state = byId("inspector-state");
  const result = byId("inspector-result");
  result.hidden = true;
  setState(state, "loading", "Loading report", observationId);
  byId("lookup-id").value = observationId;
  try {
    const response = knownItem
      ? { observation: knownItem.observation, association: { aircraft_id: knownItem.aircraft_id, mapping_id: knownItem.mapping_id } }
      : (await api(`/observations/${encodeURIComponent(observationId)}`)).body;
    const badge = byId("association-badge");
    if (response.association) {
      badge.className = "association-badge";
      badge.textContent = `Resolved to ${response.association.aircraft_id} via ${response.association.mapping_id}`;
    } else {
      badge.className = "association-badge unresolved";
      badge.textContent = "Unresolved · no mapping covers this observation time";
    }
    byId("original-json").textContent = JSON.stringify(response.observation, null, 2);
    state.hidden = true;
    result.hidden = false;
    if (window.innerWidth < 901) byId("inspector-title").scrollIntoView({ behavior: "smooth" });
  } catch (error) {
    setState(state, "error", "Could not load report", messageFrom(error));
  }
}

function renderHistory(data) {
  const state = byId("history-state");
  const results = byId("history-results");
  if (!data.history.length) {
    results.hidden = true;
    setState(state, "empty", "No matching reports", "The aircraft has no resolved reports in this time range.");
    return;
  }

  const body = byId("history-body");
  body.innerHTML = "";
  data.history.forEach((item) => {
    const observation = item.observation;
    const row = document.createElement("tr");
    const values = [
      observation.observed_at,
      observation.observation_id,
      observation.reported_identifier,
      `${formatCoordinate(observation.latitude)}, ${formatCoordinate(observation.longitude)}`,
    ];
    values.forEach((value, index) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      if (index === 1 || index === 2) cell.className = "mono";
      row.appendChild(cell);
    });
    const mappingCell = document.createElement("td");
    const mapping = document.createElement("span");
    mapping.className = "mapping-chip";
    mapping.textContent = item.mapping_id;
    mappingCell.appendChild(mapping);
    row.appendChild(mappingCell);
    const actionCell = document.createElement("td");
    const inspect = document.createElement("button");
    inspect.className = "inspect-button";
    inspect.type = "button";
    inspect.textContent = "Inspect";
    inspect.addEventListener("click", () => inspectObservation(
      observation.observation_id,
      { ...item, aircraft_id: data.aircraft_id },
    ));
    actionCell.appendChild(inspect);
    row.appendChild(actionCell);
    body.appendChild(row);
  });
  byId("result-count").textContent = `${data.count} ${data.count === 1 ? "report" : "reports"}`;
  byId("result-aircraft").textContent = `for ${data.aircraft_id}`;
  state.hidden = true;
  results.hidden = false;
}

byId("history-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const state = byId("history-state");
  const results = byId("history-results");
  results.hidden = true;
  setState(state, "loading", "Resolving history", "Matching identifiers and observation times…");
  const aircraft = byId("aircraft-id").value;
  const params = new URLSearchParams();
  if (byId("history-from").value) params.set("from", byId("history-from").value);
  if (byId("history-to").value) params.set("to", byId("history-to").value);
  try {
    const suffix = params.toString() ? `?${params}` : "";
    const { body } = await api(`/aircraft/${encodeURIComponent(aircraft)}/history${suffix}`);
    renderHistory(body);
  } catch (error) {
    setState(state, "error", "Could not load history", messageFrom(error));
  }
});

byId("lookup-form").addEventListener("submit", (event) => {
  event.preventDefault();
  inspectObservation(byId("lookup-id").value);
});
byId("observation-form").addEventListener("submit", (event) => submitJson(event, "/observations", "observation-json", "observation-status", "Report"));
byId("mapping-form").addEventListener("submit", (event) => submitJson(event, "/identity-mappings", "mapping-json", "mapping-status", "Mapping"));
byId("observation-tab").addEventListener("click", () => activateTab("observation"));
byId("mapping-tab").addEventListener("click", () => activateTab("mapping"));

checkHealth();
