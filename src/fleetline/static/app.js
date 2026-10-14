const thread = document.querySelector("#thread");
const form = document.querySelector("#composer");
const input = document.querySelector("#question");
const send = document.querySelector("#send");
const examplesEl = document.querySelector("#examples");
const healthEl = document.querySelector("#health");
const catalogView = document.querySelector("#catalog-view");
const askView = document.querySelector("#ask-view");

let sessionId = null;
let catalog = null;

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([key, value]) => {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  });
  (children || []).forEach((child) => node.append(child));
  return node;
}

function formatValue(value, format) {
  if (value == null || Number.isNaN(Number(value))) return "n/a";
  const number = Number(value);
  if (format === "currency") {
    const digits = Math.abs(number) >= 100 ? 0 : 2;
    return number.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits });
  }
  if (format === "unit_price") {
    return number.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  if (format === "percent") return `${(number * 100).toFixed(1)}%`;
  if (format === "gallons") return `${Math.round(number).toLocaleString()} gal`;
  if (format === "days") return `${number.toFixed(1)} days`;
  return Math.round(number).toLocaleString();
}

function compact(value, format) {
  if (format === "percent") return `${(Number(value) * 100).toFixed(0)}%`;
  const number = Math.abs(Number(value));
  const sign = Number(value) < 0 ? "-" : "";
  let body;
  if (number >= 1e6) body = `${(number / 1e6).toFixed(1)}M`;
  else if (number >= 1e3) body = `${(number / 1e3).toFixed(1)}K`;
  else body = number.toFixed(format === "unit_price" ? 2 : 0);
  if (format === "currency" || format === "unit_price") return `${sign}$${body}`;
  return sign + body;
}

function labelOf(row, spec) {
  return (spec.group_by || []).map((key) => row[key]).join(" · ");
}

function drawChart(rows, spec, format) {
  const chartRows = rows.filter((row) => row.value != null);
  if (!chartRows.length || !spec.group_by || !spec.group_by.length) return null;
  const line = spec.order_by === "month" || spec.group_by.includes("month");
  const data = line ? chartRows : chartRows.slice(0, 12);
  const width = 640;
  const max = Math.max(...data.map((row) => Number(row.value) || 0), 0.0001);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  if (line) {
    const height = 220;
    const pad = 28;
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    const step = data.length === 1 ? 0 : (width - pad * 2) / (data.length - 1);
    const coords = data.map((row, index) => {
      const x = pad + index * step;
      const y = height - pad - ((Number(row.value) || 0) / max) * (height - pad * 2);
      return [x, y, labelOf(row, spec)];
    });
    const lineNode = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    lineNode.setAttribute("fill", "none");
    lineNode.setAttribute("stroke", "#0f6e56");
    lineNode.setAttribute("stroke-width", "3");
    lineNode.setAttribute("points", coords.map(([x, y]) => `${x},${y}`).join(" "));
    svg.append(lineNode);
    coords.forEach(([x, y, label], index) => {
      const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot.setAttribute("cx", x);
      dot.setAttribute("cy", y);
      dot.setAttribute("r", "4");
      dot.setAttribute("fill", "#f0b429");
      svg.append(dot);
      if (index === 0 || index === coords.length - 1 || index === Math.floor(coords.length / 2)) {
        const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
        text.setAttribute("x", x);
        text.setAttribute("y", height - 8);
        text.setAttribute("text-anchor", "middle");
        text.setAttribute("font-size", "11");
        text.setAttribute("fill", "#5d675f");
        text.textContent = label;
        svg.append(text);
      }
    });
  } else {
    const rowH = 32;
    const height = data.length * rowH + 8;
    const labelW = 168;
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    data.forEach((row, index) => {
      const y = index * rowH + 6;
      const label = labelOf(row, spec);
      const barW = Math.max(2, ((Number(row.value) || 0) / max) * (width - labelW - 70));
      const name = document.createElementNS("http://www.w3.org/2000/svg", "text");
      name.setAttribute("x", "0");
      name.setAttribute("y", y + 16);
      name.setAttribute("font-size", "12");
      name.setAttribute("fill", "#17211c");
      name.textContent = label.length > 22 ? `${label.slice(0, 21)}…` : label;
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", labelW);
      rect.setAttribute("y", y);
      rect.setAttribute("width", barW);
      rect.setAttribute("height", "18");
      rect.setAttribute("rx", "6");
      rect.setAttribute("fill", "#0f6e56");
      const amount = document.createElementNS("http://www.w3.org/2000/svg", "text");
      amount.setAttribute("x", labelW + barW + 8);
      amount.setAttribute("y", y + 14);
      amount.setAttribute("font-size", "12");
      amount.setAttribute("fill", "#5d675f");
      amount.textContent = compact(row.value, format);
      svg.append(name, rect, amount);
    });
  }
  const wrap = el("div", { class: "chart" });
  wrap.append(svg);
  return wrap;
}

function chips(spec) {
  const wrap = el("div", { class: "chips" });
  const bits = [spec.metric];
  if (spec.group_by.length) bits.push(`by ${spec.group_by.join(", ")}`);
  spec.filters.forEach((item) => bits.push(`${item.dimension}: ${item.values.join(", ")}`));
  bits.push(spec.time_range.label);
  if (spec.limit) bits.push(`limit ${spec.limit}`);
  bits.forEach((bit) => wrap.append(el("span", { class: "chip", text: bit })));
  return wrap;
}

function table(rows, spec, format) {
  const shown = rows;
  const keys = spec.group_by.concat(["value"]);
  const node = document.createElement("table");
  const head = document.createElement("tr");
  keys.forEach((key) => {
    const cell = document.createElement("th");
    cell.textContent = key === "value" ? "Value" : key.replaceAll("_", " ");
    if (key === "value") cell.className = "num";
    head.append(cell);
  });
  node.append(head);
  shown.forEach((row) => {
    const line = document.createElement("tr");
    keys.forEach((key) => {
      const cell = document.createElement("td");
      cell.textContent = key === "value" ? formatValue(row[key], format) : String(row[key] ?? "");
      if (key === "value") cell.className = "num";
      line.append(cell);
    });
    node.append(line);
  });
  return node;
}

function renderAnswer(result) {
  const card = el("article", { class: "card" });
  card.append(el("p", { text: result.message }));
  if (result.status === "clarify") {
    const row = el("div", { class: "suggestions" });
    (result.suggestions || []).forEach((question) => {
      const button = el("button", { class: "suggestion", type: "button", text: question });
      button.addEventListener("click", () => submit(question));
      row.append(button);
    });
    card.append(row);
    return card;
  }
  const spec = result.spec;
  const format = result.highlight ? result.highlight.format : "count";
  if (result.highlight && result.highlight.kind === "total") {
    card.append(el("p", { class: "hero", text: formatValue(result.highlight.value, format) }));
  } else if (result.highlight) {
    const kind = result.highlight.kind === "peak" ? "Peak" : "Top";
    card.append(el("p", { class: "kicker", text: `${kind} · ${result.highlight.label} · ${formatValue(result.highlight.value, format)}` }));
  }
  if (result.chart && spec.group_by.length) {
    const chart = drawChart(result.rows, spec, format);
    if (chart) card.append(chart);
  }
  if (result.rows && result.rows.length && spec.group_by.length) card.append(table(result.rows, spec, format));
  card.append(chips(spec));
  const details = el("details");
  details.append(el("summary", { text: "How this was answered" }));
  const sql = el("pre");
  sql.textContent = `${result.sql}\n\nparams: ${JSON.stringify(result.params)}`;
  details.append(sql);
  card.append(details);
  return card;
}

function pushUser(question) {
  thread.append(el("div", { class: "bubble", text: question }));
}

async function submit(question) {
  const text = question.trim();
  if (!text) return;
  input.value = "";
  if (thread.querySelector(".empty")) thread.replaceChildren();
  pushUser(text);
  send.disabled = true;
  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text, session_id: sessionId }),
    });
    const body = await response.json();
    if (!response.ok) {
      thread.append(el("article", { class: "card" }, [el("p", { text: body.detail || "The question was rejected." })]));
      return;
    }
    sessionId = body.session_id;
    thread.append(renderAnswer(body));
  } catch (error) {
    thread.append(el("article", { class: "card" }, [el("p", { text: "Fleetline is not reachable." })]));
  } finally {
    send.disabled = false;
    thread.scrollTop = thread.scrollHeight;
    input.focus();
  }
}

function showEmpty() {
  thread.replaceChildren(el("p", {
    class: "empty",
    text: "Ask a question about the synthetic portfolio. A follow-up stays on the same metric until you name a new one.",
  }));
}

function renderExamples() {
  examplesEl.replaceChildren();
  const areas = [];
  (catalog.examples || []).forEach((example) => {
    if (!areas.includes(example.area)) areas.push(example.area);
  });
  areas.forEach((area) => {
    examplesEl.append(el("div", { class: "area", text: area }));
    catalog.examples.filter((example) => example.area === area).forEach((example) => {
      const button = el("button", { type: "button", text: example.question });
      button.addEventListener("click", () => submit(example.question));
      examplesEl.append(button);
    });
  });
}

function renderCatalog() {
  const metrics = el("div");
  metrics.append(el("h2", { text: "Metrics" }));
  catalog.metrics.forEach((metric) => {
    const card = el("article", { class: "def-card" });
    card.append(el("h3", { text: metric.label }));
    card.append(el("p", { text: metric.description }));
    card.append(el("p", { text: `Also called: ${metric.synonyms.join(", ")}` }));
    metrics.append(card);
  });
  const dimensions = el("div");
  dimensions.append(el("h2", { text: "Breakdowns" }));
  catalog.dimensions.forEach((dimension) => {
    const card = el("article", { class: "def-card" });
    card.append(el("h3", { text: dimension.label }));
    card.append(el("p", { text: dimension.description || dimension.facts.join(", ") }));
    if (dimension.values.length) card.append(el("p", { text: dimension.values.join(", ") }));
    dimensions.append(card);
  });
  const wrap = el("div", { class: "defs" }, [metrics, dimensions]);
  catalogView.replaceChildren(wrap);
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    const ask = tab.dataset.view === "ask";
    askView.hidden = !ask;
    catalogView.hidden = ask;
  });
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  submit(input.value);
});

document.querySelector("#new-chat").addEventListener("click", () => {
  sessionId = null;
  showEmpty();
  input.focus();
});

showEmpty();
input.focus();

fetch("/api/health")
  .then((response) => response.json())
  .then((body) => {
    const rows = body.rows || {};
    healthEl.textContent = `As of ${body.as_of} · ${Number(rows.transactions || 0).toLocaleString()} transactions · semantic v${body.semantic_version}`;
  })
  .catch(() => {
    healthEl.textContent = "Portfolio unavailable";
  });

fetch("/api/catalog")
  .then((response) => response.json())
  .then((body) => {
    catalog = body;
    renderExamples();
    renderCatalog();
  })
  .catch(() => {
    examplesEl.textContent = "Examples unavailable";
  });
