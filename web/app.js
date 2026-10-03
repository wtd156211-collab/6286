const PAGE_SIZE = 2000;

async function loadText(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${path} 加载失败：HTTP ${response.status}`);
  }
  return response.text();
}

function parseJsonl(text) {
  return text
    .split("\n")
    .filter((line) => line.length > 0)
    .map((line) => JSON.parse(line));
}

function parseSources(text) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  if (lines.length > 0 && lines[lines.length - 1] === "") {
    lines.pop();
  }
  return lines;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatValue(value) {
  if (Array.isArray(value)) {
    return `${value[0]} ~ ${value[1]}`;
  }
  return value === null || value === undefined ? "—" : String(value);
}

function renderSummary(records) {
  const total = records.length;
  const counts = { ok: 0, empty: 0, reject: 0 };
  const reasonCounts = new Map();
  for (const record of records) {
    counts[record.status] += 1;
    if (record.status === "reject") {
      reasonCounts.set(record.code, (reasonCounts.get(record.code) || 0) + 1);
    }
  }
  const rate = total === 0 ? 0 : ((counts.ok / total) * 100).toFixed(2);

  const cards = [
    ["总行数", total, ""],
    ["成功率", `${rate}%`, "success"],
    ["成功", counts.ok, "success"],
    ["空值", counts.empty, ""],
    ["拒绝", counts.reject, "reject"],
  ];
  const cardsHtml = cards
    .map(
      ([label, number, cls]) =>
        `<div class="card ${cls}"><div class="label">${label}</div>` +
        `<div class="number">${number}</div></div>`,
    )
    .join("");

  const sortedReasons = [...reasonCounts.entries()].sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
  );
  const reasonsHtml =
    `<div class="card reasons"><div class="label">拒绝原因分布</div>` +
    sortedReasons
      .map(([code, count]) => {
        const percent = total === 0 ? 0 : ((count / counts.reject) * 100).toFixed(1);
        return (
          `<div class="reason-row"><span class="code">${escapeHtml(code)}</span>` +
          `<div class="bar"><span style="width:${percent}%"></span></div>` +
          `<span>${count} 条</span></div>`
        );
      })
      .join("") +
    `</div>`;

  document.querySelector("#summary").innerHTML = cardsHtml + reasonsHtml;
}

function statusCell(record) {
  if (record.status === "ok") {
    return '<span class="status-ok">成功</span>';
  }
  if (record.status === "empty") {
    return '<span>空值 <span class="code">EMPTY</span></span>';
  }
  const candidates = record.candidates
    ? `<span class="candidates">可能含义：${record.candidates
        .map(escapeHtml)
        .join(" / ")}</span>`
    : "";
  return `<span class="code">${escapeHtml(record.code)}</span>${candidates}`;
}

function renderRows(records, sources, limit) {
  const body = document.querySelector("#rows");
  const shown = Math.min(limit, records.length);
  const parts = [];
  for (let index = 0; index < shown; index += 1) {
    const record = records[index];
    const source = sources[index] !== undefined ? sources[index] : "—";
    const ok = record.status === "ok";
    parts.push(
      `<tr class="${escapeHtml(record.status)}">` +
        `<td>${record.line}</td>` +
        `<td class="source">${escapeHtml(source) || "&nbsp;"}</td>` +
        `<td class="col-value">${ok ? escapeHtml(formatValue(record.value)) : "—"}</td>` +
        `<td class="col-unit">${ok && record.unit ? escapeHtml(record.unit) : "—"}</td>` +
        `<td class="col-normalized">${ok ? escapeHtml(record.normalized) : "—"}</td>` +
        `<td>${statusCell(record)}</td>` +
        `</tr>`,
    );
  }
  body.innerHTML = parts.join("");
  document.querySelector("#rendered-count").textContent =
    `已渲染 ${shown} / ${records.length} 行`;
  document.querySelector("#load-more").disabled = shown >= records.length;
}

async function main() {
  let records;
  let sources = [];
  try {
    const [jsonl, sourceText] = await Promise.all([
      loadText("data.jsonl"),
      loadText("data.txt").catch(() => ""),
    ]);
    records = parseJsonl(jsonl);
    sources = sourceText ? parseSources(sourceText) : [];
  } catch (error) {
    document.querySelector("main").insertAdjacentHTML(
      "afterbegin",
      `<p id="error">${escapeHtml(error.message)}。请用 ` +
        "<code>python -m http.server 8000</code> 后访问本页。</p>",
    );
    return;
  }

  renderSummary(records);
  let limit = PAGE_SIZE;
  renderRows(records, sources, limit);
  document.querySelector("#load-more").addEventListener("click", () => {
    limit += PAGE_SIZE;
    renderRows(records, sources, limit);
  });
}

main();
