// 純工具
export function dedupeById(arr) {
  const seen = new Set();
  return arr.filter(({ id }) => seen.has(id) ? false : (seen.add(id), true));
}

export function extractUnitFromPath(p) {
  const m = /第(\d+)單元/.exec(p || '');
  return m ? parseInt(m[1], 10) : null;
}

export function normDifficultyLabel(s) {
  const v = String(s || '').trim().toLowerCase();
  if (v === 'easy' || v === 'medium' || v === 'hard') return v;
  return 'unknown';
}

export function groupByUnitAndDifficulty(entries) {
  const units = new Map(); // unit -> Map(diff -> items[])
  for (const it of entries) {
    const unit = it.unit ?? extractUnitFromPath(it.file) ?? 0;
    const diff = normDifficultyLabel(it.difficulty);
    if (!units.has(unit)) units.set(unit, new Map());
    const diffMap = units.get(unit);
    if (!diffMap.has(diff)) diffMap.set(diff, []);
    diffMap.get(diff).push(it);
  }
  return units;
}

export function indentLines(text, pad = '  ') {
  return String(text || '')
    .trim()
    .split('\n')
    .map((line) => pad + line.trim())
    .join('\n');
}