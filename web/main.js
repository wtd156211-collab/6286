// parsebot 结果查看页：只消费引擎产出的 JSONL，不做任何二次解析或猜测。
// 原文来自与输入逐行对应的 input.txt（可选；缺失时只显示行号）。

const PAGE_SIZE = 2000;

const CODE_LABELS = {
  EMPTY: "空值",
  AMBIGUOUS_UNIT: "单位歧义",
  AMBIGUOUS_NUMBER: "千分位歧义",
  UNPARSEABLE: "无法解析",
  UNIT_MISMATCH: "量纲不一致",
  INVALID_RANGE: "区间倒序",
  OUT_OF_RANGE: "越界",
};

async function fetchText(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${path} -> ${response.status}`);
  }
  return response.text();
}

// 与 CLI 的分行口径保持一致：末尾换行不算一行。
function splitLines(text) {
  if (text === "") return [];
  const body = text.endsWith("\n") ? text.slice(0, -1) : text;
  return body.split("\n").map((line) =>
    line.endsWith("\r") ? line.slice(0, -1) : line
  );
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderStats(records) {
  const total = records.length;
  const counts = { ok: 0, empty: 0, reject: 0 };
  const codeCounts = {};
  for (const record of records) {
    counts[record.status] = (counts[record.status] ?? 0) + 1;
    if (record.status !== "ok") {
      codeCounts[record.code] = (codeCounts[record.code] ?? 0) + 1;
    }
  }
  const rate = total === 0 ? 0 : (counts.ok / total) * 100;

  document.getElementById("summary").innerHTML =
    `<span class="rate">${rate.toFixed(2)}%</span>` +
    `成功 ${counts.ok} / 共 ${total} 行` +
    `　空值 ${counts.empty}　拒绝 ${counts.reject}`;

  const distribution = document.getElementById("distribution");
  distribution.replaceChildren();
  for (const code of Object.keys(codeCounts).sort()) {
    const pill = document.createElement("span");
    pill.className = "pill" + (code === "EMPTY" ? " empty-pill" : "");
    pill.textContent = `${code}（${CODE_LABELS[code] ?? "未知"}）: ${codeCounts[code]}`;
    distribution.append(pill);
  }
}

function statusCell(record) {
  if (record.status === "ok") {
    return `<span>成功</span>`;
  }
  if (record.status === "empty") {
    return `<span class="code">EMPTY</span> <span>空值（不算拒绝）</span>`;
  }
  let html = `<span class="code">${escapeHtml(record.code)}</span>`;
  html += ` <span>${escapeHtml(CODE_LABELS[record.code] ?? "拒绝")}</span>`;
  if (Array.isArray(record.candidates) && record.candidates.length > 0) {
    html += `<span class="candidates">候选：${record.candidates
      .map((candidate) => escapeHtml(candidate))
      .join("、")}</span>`;
  }
  return html;
}

function makeRow(record, original) {
  const tr = document.createElement("tr");
  tr.className = record.status;
  const value = record.status === "ok" ? JSON.stringify(record.value) : "—";
  const unit = record.status === "ok" && record.unit !== null ? record.unit : "—";
  const normalized = record.status === "ok" ? record.normalized : "";
  const source = original === undefined ? "（无原文）" : original;
  tr.innerHTML =
    `<td>${record.line}</td>` +
    `<td class="col-text">${escapeHtml(source)}</td>` +
    `<td class="col-value">${escapeHtml(value)}</td>` +
    `<td class="col-unit">${escapeHtml(unit)}</td>` +
    `<td class="col-norm">${escapeHtml(normalized)}</td>` +
    `<td class="col-status">${statusCell(record)}</td>`;
  return tr;
}

let allRecords = [];
let allOriginals = [];
let rendered = 0;

function renderPage() {
  const body = document.getElementById("result-body");
  const end = Math.min(rendered + PAGE_SIZE, allRecords.length);
  const fragment = document.createDocumentFragment();
  for (let index = rendered; index < end; index += 1) {
    fragment.append(makeRow(allRecords[index], allOriginals[index]));
  }
  body.append(fragment);
  rendered = end;

  const button = document.getElementById("load-more");
  button.hidden = rendered >= allRecords.length;
  document.getElementById("rendered-count").textContent =
    `已渲染 ${rendered} / ${allRecords.length} 行（统计按全量计算）`;
}

async function main() {
  const dataText = await fetchText("data.jsonl");
  allRecords = splitLines(dataText)
    .filter((line) => line.length > 0)
    .map((line) => JSON.parse(line));

  try {
    const inputText = await fetchText("input.txt");
    allOriginals = splitLines(inputText);
  } catch {
    allOriginals = [];
  }

  renderStats(allRecords);
  document.getElementById("load-more").addEventListener("click", renderPage);
  renderPage();
}

main().catch((error) => {
  document.getElementById("summary").textContent =
    `加载失败：${error.message}（请用 python -m http.server 8000 从仓库根目录启动）`;
});
