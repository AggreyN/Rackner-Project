// CSV export of the obligation register — the "take it with you" moment.
// Excel-friendly: quoted cells, CRLF rows, UTF-8 BOM.

import type { Obligation } from "./types";

const COLUMNS: [string, (o: Obligation) => string | number | null][] = [
  ["Obligation", (o) => o.plain_english_text],
  ["Type", (o) => o.obligation_type],
  ["Category", (o) => o.category],
  ["Time bucket", (o) => o.time_bucket],
  ["Trigger / deadline", (o) => o.trigger_or_deadline],
  ["Responsible party", (o) => o.responsible_party],
  ["Relevant roles", (o) => o.roles.join("; ")],
  ["Status", (o) => o.status],
  ["Page", (o) => o.page],
  ["Quote verified", (o) => (o.verified ? "yes" : "NO — flagged")],
  ["Confidence", (o) => (o.confidence != null ? `${Math.round(o.confidence * 100)}%` : null)],
  ["Verbatim quote", (o) => o.verbatim_quote],
];

function cell(v: string | number | null): string {
  if (v == null) return "";
  return `"${String(v).replace(/"/g, '""')}"`;
}

export function registerToCsv(obligations: Obligation[]): string {
  const header = COLUMNS.map(([name]) => cell(name)).join(",");
  const rows = obligations.map((o) => COLUMNS.map(([, get]) => cell(get(o))).join(","));
  return "﻿" + [header, ...rows].join("\r\n");
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
