// 將文字轉成表格
export function renderTabbedTable(block) {
  if (typeof block !== "string") return null;
  if (block.includes("\\t")) block = block.replace(/\\t/g, "\t");
  block = block.replace(/^\uFEFF/, "");

  const lines = block
    .split(/\r?\n/)
    .map(s => s.replace(/\s+$/, ""))
    .filter(Boolean);

  if (!lines.length) return null;

  const headIdx = lines.findIndex(l => l.includes("\t"));
  if (headIdx === -1) return null;

  const title = headIdx > 0 ? lines.slice(0, headIdx).join(" / ") : null;
  const headerCells = lines[headIdx].split(/\t+/).map(s => s.trim()).filter(Boolean);
  const rows = lines.slice(headIdx + 1).filter(l => l.includes("\t"));
  if (headerCells.length < 2 || rows.length === 0) return null;

  const wrap = document.createElement("div");
  wrap.className = "data-table-wrap";
  if (title) {
    const h = document.createElement("h4");
    h.className = "data-table-title";
    h.textContent = title;
    wrap.appendChild(h);
  }

  const table = document.createElement("table");
  table.className = "data-table";

  const thead = document.createElement("thead");
  const trh = document.createElement("tr");
  headerCells.forEach(hd => {
    const th = document.createElement("th");
    th.textContent = hd;
    trh.appendChild(th);
  });
  thead.appendChild(trh);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach(line => {
    const cells = line.split(/\t+/);
    const tr = document.createElement("tr");
    headerCells.forEach((_, i) => {
      const td = document.createElement("td");
      const cell = (cells[i] ?? "").trim();
      if (i === 0 || /→|\(|\)|'|"|\[|\]|True|False|None/.test(cell)) {
        const code = document.createElement("code");
        code.className = "nohighlight";
        code.textContent = cell;  // 用 textContent，保留字面上的 \n
        td.appendChild(code);
      } else {
        td.textContent = cell;
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}
