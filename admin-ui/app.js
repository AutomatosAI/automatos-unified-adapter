const DEFAULT_BASE = "http://localhost:8000";

const state = {
  tools: [],
  activeTool: null,
};

const baseUrlInput = document.getElementById("baseUrl");
const tokenInput = document.getElementById("authToken");
const statusPill = document.getElementById("connectionStatus");
const toolsTable = document.getElementById("toolsTable");
const activityLog = document.getElementById("activityLog");
const modalBackdrop = document.getElementById("modalBackdrop");
const modalTitle = document.getElementById("modalTitle");
const modalSubtitle = document.getElementById("modalSubtitle");
const toolForm = document.getElementById("toolForm");
const formError = document.getElementById("formError");
const deleteBtn = document.getElementById("deleteTool");

const templates = {
  petstore: {
    name: "Petstore",
    description: "Demo Petstore REST tools",
    provider: "petstore",
    category: "demo",
    adapter_type: "rest",
    openapi_url: "https://petstore3.swagger.io/api/v3/openapi.json",
    base_url: "https://petstore3.swagger.io/api/v3",
    operation_ids: [],
    auth_config: {},
    tags: ["demo", "openapi"],
    credential_mode: "byo",
  },
  httpbin: {
    name: "Httpbin",
    description: "Httpbin demo REST API",
    provider: "httpbin",
    category: "demo",
    adapter_type: "rest",
    openapi_url: "https://httpbin.org/spec.json",
    base_url: "https://httpbin.org",
    operation_ids: [],
    auth_config: {},
    tags: ["demo", "httpbin"],
    credential_mode: "byo",
  },
  github: {
    name: "GitHub",
    description: "GitHub public REST API",
    provider: "github",
    category: "devtools",
    adapter_type: "rest",
    openapi_url:
      "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json",
    base_url: "https://api.github.com",
    operation_ids: [],
    auth_config: {},
    tags: ["github", "openapi"],
    credential_mode: "byo",
  },
};

function log(message) {
  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
  activityLog.prepend(entry);
}

function setStatus(text, ok = false) {
  statusPill.textContent = text;
  statusPill.style.borderColor = ok ? "rgba(16, 185, 129, 0.6)" : "var(--border)";
  statusPill.style.color = ok ? "#34d399" : "var(--text-muted)";
}

function getConfig() {
  const baseUrl = baseUrlInput.value.trim() || DEFAULT_BASE;
  const token = tokenInput.value.trim();
  return { baseUrl, token };
}

async function apiFetch(path, options = {}) {
  const { baseUrl, token } = getConfig();
  if (!token) {
    throw new Error("Missing admin token");
  }
  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
    ...(options.headers || {}),
  };
  const response = await fetch(`${baseUrl}${path}`, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed (${response.status})`);
  }
  return response.json();
}

function renderTools() {
  toolsTable.innerHTML = "";
  if (!state.tools.length) {
    toolsTable.innerHTML =
      "<p class='tool-meta'>No tools found. Create a new one.</p>";
    return;
  }
  state.tools.forEach((tool) => {
    const row = document.createElement("div");
    row.className = "tool-row";
    row.innerHTML = `
      <div>
        <h4>${tool.name}</h4>
        <div class="tool-meta">${tool.description || "No description"}</div>
      </div>
      <div class="tool-meta">${tool.provider}</div>
      <div class="tool-pill">${tool.adapter_type.toUpperCase()}</div>
      <div class="tool-meta">${tool.enabled ? "Enabled" : "Disabled"}</div>
      <div class="tool-actions">
        <button class="ghost-btn" data-action="edit">Edit</button>
        <button class="ghost-btn" data-action="toggle">${
          tool.enabled ? "Disable" : "Enable"
        }</button>
      </div>
    `;
    row.querySelector('[data-action="edit"]').addEventListener("click", () => {
      openModal(tool);
    });
    row.querySelector('[data-action="toggle"]').addEventListener("click", () => {
      toggleTool(tool);
    });
    toolsTable.appendChild(row);
  });
}

async function loadTools() {
  try {
    const data = await apiFetch("/admin/tools");
    state.tools = data;
    renderTools();
    setStatus("Connected", true);
    log("Tools loaded");
  } catch (error) {
    setStatus("Disconnected", false);
    log(`Failed to load tools: ${error.message}`);
  }
}

function openModal(tool = null) {
  state.activeTool = tool;
  toolForm.reset();
  formError.classList.add("hidden");
  deleteBtn.classList.toggle("hidden", !tool);
  modalTitle.textContent = tool ? "Edit Tool" : "Create Tool";
  modalSubtitle.textContent = tool
    ? `Update ${tool.name} metadata`
    : "Define tool metadata for the adapter.";

  if (tool) {
    toolForm.name.value = tool.name || "";
    toolForm.provider.value = tool.provider || "";
    toolForm.category.value = tool.category || "";
    toolForm.adapter_type.value = tool.adapter_type || "rest";
    toolForm.description.value = tool.description || "";
    toolForm.openapi_url.value = tool.openapi_url || "";
    toolForm.base_url.value = tool.base_url || "";
    toolForm.credential_mode.value = tool.credential_mode || "hosted";
    toolForm.enabled.value = tool.enabled ? "true" : "false";
    toolForm.tags.value = JSON.stringify(tool.tags || []);
    toolForm.operation_ids.value = JSON.stringify(tool.operation_ids || []);
    toolForm.auth_config.value = JSON.stringify(tool.auth_config || {});
    toolForm.mcp_server_url.value = tool.mcp_server_url || "";
    toolForm.credential_id.value = tool.credential_id || "";
    toolForm.credential_name.value = tool.credential_name || "";
    toolForm.credential_environment.value =
      tool.credential_environment || "production";
  } else {
    toolForm.tags.value = "[]";
    toolForm.operation_ids.value = "[]";
    toolForm.auth_config.value = "{}";
    toolForm.credential_environment.value = "production";
  }

  modalBackdrop.classList.remove("hidden");
}

function closeModal() {
  modalBackdrop.classList.add("hidden");
  state.activeTool = null;
}

function parseJsonField(value, fieldName) {
  if (!value.trim()) return null;
  try {
    return JSON.parse(value);
  } catch (error) {
    throw new Error(`${fieldName} must be valid JSON`);
  }
}

function buildPayload(form) {
  const tags = parseJsonField(form.tags.value || "[]", "Tags") || [];
  const operationIds =
    parseJsonField(form.operation_ids.value || "[]", "Operation IDs") || [];
  const authConfig =
    parseJsonField(form.auth_config.value || "{}", "Auth Config") || {};

  return {
    name: form.name.value.trim(),
    description: form.description.value.trim(),
    provider: form.provider.value.trim(),
    category: form.category.value.trim(),
    adapter_type: form.adapter_type.value,
    enabled: form.enabled.value === "true",
    openapi_url: form.openapi_url.value.trim() || null,
    base_url: form.base_url.value.trim() || null,
    mcp_server_url: form.mcp_server_url.value.trim() || null,
    operation_ids: operationIds,
    auth_config: authConfig,
    tags: tags,
    credential_mode: form.credential_mode.value,
    credential_id: form.credential_id.value ? Number(form.credential_id.value) : null,
    credential_name: form.credential_name.value.trim() || null,
    credential_environment: form.credential_environment.value.trim() || "production",
  };
}

toolForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.classList.add("hidden");
  try {
    const payload = buildPayload(toolForm);
    if (state.activeTool?.id) {
      await apiFetch(`/admin/tools/${state.activeTool.id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      log(`Updated tool: ${payload.name}`);
    } else {
      await apiFetch("/admin/tools", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      log(`Created tool: ${payload.name}`);
    }
    closeModal();
    await loadTools();
  } catch (error) {
    formError.textContent = error.message;
    formError.classList.remove("hidden");
  }
});

deleteBtn.addEventListener("click", async () => {
  if (!state.activeTool) return;
  try {
    await apiFetch(`/admin/tools/${state.activeTool.id}`, { method: "DELETE" });
    log(`Deleted tool: ${state.activeTool.name}`);
    closeModal();
    await loadTools();
  } catch (error) {
    formError.textContent = error.message;
    formError.classList.remove("hidden");
  }
});

async function toggleTool(tool) {
  try {
    await apiFetch(`/admin/tools/${tool.id}`, {
      method: "PUT",
      body: JSON.stringify({ enabled: !tool.enabled }),
    });
    log(`Toggled ${tool.name} to ${tool.enabled ? "disabled" : "enabled"}`);
    await loadTools();
  } catch (error) {
    log(`Failed to toggle tool: ${error.message}`);
  }
}

document.getElementById("refreshTools").addEventListener("click", loadTools);
document.getElementById("openCreate").addEventListener("click", () => openModal());
document.getElementById("closeModal").addEventListener("click", closeModal);
document.getElementById("clearLog").addEventListener("click", () => {
  activityLog.innerHTML = "";
});

document.getElementById("connectBtn").addEventListener("click", loadTools);
document.getElementById("clearBtn").addEventListener("click", () => {
  baseUrlInput.value = DEFAULT_BASE;
  tokenInput.value = "";
  setStatus("Disconnected", false);
});

document.querySelectorAll(".template").forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.dataset.template;
    openModal(templates[key]);
  });
});

modalBackdrop.addEventListener("click", (event) => {
  if (event.target === modalBackdrop) {
    closeModal();
  }
});

baseUrlInput.value = DEFAULT_BASE;
setStatus("Disconnected", false);
log("Ready for connection.");
