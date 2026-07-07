// Thin API client — every backend call lives here, nowhere else.
// Change the backend URL or a route once, and the whole app follows.

import type { DocumentMeta, ObligationGroups, RoleInfo, ScanResult } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export async function scanDocument(file: File): Promise<ScanResult> {
  const form = new FormData();
  form.append("file", file);
  return json(await fetch(`${BASE}/documents/scan`, { method: "POST", body: form }));
}

export async function uploadDocument(
  file: File,
  piiAcknowledged: boolean
): Promise<{ id: number; status: string; expires_at: string }> {
  const form = new FormData();
  form.append("file", file);
  form.append("pii_acknowledged", String(piiAcknowledged));
  return json(await fetch(`${BASE}/documents`, { method: "POST", body: form }));
}

export async function getDocument(id: number): Promise<DocumentMeta> {
  return json(await fetch(`${BASE}/documents/${id}`));
}

export function documentPdfUrl(id: number): string {
  return `${BASE}/documents/${id}/pdf`;
}

export async function getRoles(): Promise<RoleInfo[]> {
  return json(await fetch(`${BASE}/obligations/roles`));
}

export async function getObligations(
  docId: number,
  role: string | null,
  groupBy: string
): Promise<ObligationGroups> {
  const params = new URLSearchParams({ group_by: groupBy });
  if (role) params.set("role", role);
  return json(await fetch(`${BASE}/obligations/document/${docId}?${params}`));
}

export async function updateObligationStatus(id: number, status: string): Promise<void> {
  await json(await fetch(`${BASE}/obligations/${id}?status=${status}`, { method: "PATCH" }));
}
