// Span-level citation matching: find a verbatim quote inside a PDF page's
// text layer and say exactly which characters of which text items to mark.
// PDF text comes fragmented (one item per line or run), so we normalize
// whitespace on both sides while keeping a map back to the original chars.

export interface ItemRange {
  item: number;  // text-item index within the page
  start: number; // char offset into the item's original string
  end: number;   // exclusive
}

export function findQuoteRanges(items: string[], quote: string): ItemRange[] {
  const q = quote.replace(/\s+/g, " ").trim().toLowerCase();
  if (!q) return [];

  // Build the normalized page string with a per-char map to (item, char).
  let norm = "";
  const map: { item: number; char: number }[] = [];
  let lastWasSpace = true;
  items.forEach((str, itemIndex) => {
    for (let c = 0; c < str.length; c++) {
      const ch = str[c];
      if (/\s/.test(ch)) {
        if (!lastWasSpace) {
          norm += " ";
          map.push({ item: itemIndex, char: c });
          lastWasSpace = true;
        }
      } else {
        norm += ch.toLowerCase();
        map.push({ item: itemIndex, char: c });
        lastWasSpace = false;
      }
    }
    // Items usually break at line ends — treat the boundary as whitespace.
    if (!lastWasSpace) {
      norm += " ";
      map.push({ item: itemIndex, char: str.length });
      lastWasSpace = true;
    }
  });

  const at = norm.indexOf(q);
  if (at === -1) return [];

  // Collapse the matched normalized chars into contiguous per-item ranges.
  const ranges: ItemRange[] = [];
  for (let n = at; n < at + q.length; n++) {
    const { item, char } = map[n];
    const last = ranges[ranges.length - 1];
    if (last && last.item === item && char <= last.end) {
      last.end = Math.max(last.end, char + 1);
    } else {
      ranges.push({ item, start: char, end: char + 1 });
    }
  }
  return ranges;
}

const HTML_ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
};

export function escapeHtml(s: string): string {
  return s.replace(/[&<>"]/g, (c) => HTML_ESCAPES[c]);
}

// HTML for one text item, with its matched slices wrapped in a glowing <mark>.
export function renderItemHtml(str: string, ranges: ItemRange[], itemIndex: number): string {
  const mine = ranges
    .filter((r) => r.item === itemIndex)
    .sort((a, b) => a.start - b.start);
  if (mine.length === 0) return escapeHtml(str);

  let html = "";
  let cursor = 0;
  for (const r of mine) {
    const start = Math.max(cursor, Math.min(r.start, str.length));
    const end = Math.min(r.end, str.length);
    if (end <= start) continue;
    html += escapeHtml(str.slice(cursor, start));
    html += `<mark class="anvil-glow">${escapeHtml(str.slice(start, end))}</mark>`;
    cursor = end;
  }
  html += escapeHtml(str.slice(cursor));
  return html;
}
