// Thin API client — every backend call lives here, nowhere else.
// Change the backend URL or a route once, and the whole app follows.
//
// When NEXT_PUBLIC_API_URL is unset, every call routes to the in-browser
// mock (lib/mock.ts) so the UI runs with no backend — same trick as the
// backend's extractor adapter falling back to a mock without an API key.

import type { DocumentMeta, ObligationGroups, RoleInfo, ScanResult } from "./types";
import * as mock from "./mock";

const BASE = process.env.NEXT_PUBLIC_API_URL;
const USE_MOCK = !BASE;

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export async function scanDocument(file: File): Promise<ScanResult> {
  if (USE_MOCK) return mock.scanDocument(file);
  const form = new FormData();
  form.append("file", file);
  return json(await fetch(`${BASE}/documents/scan`, { method: "POST", body: form }));
}

export async function uploadDocument(
  file: File,
  piiAcknowledged: boolean
): Promise<{ id: number; status: string; expires_at: string }> {
  if (USE_MOCK) return mock.uploadDocument(file, piiAcknowledged);
  const form = new FormData();
  form.append("file", file);
  form.append("pii_acknowledged", String(piiAcknowledged));
  return json(await fetch(`${BASE}/documents`, { method: "POST", body: form }));
}

export async function getDocument(id: number): Promise<DocumentMeta> {
  if (USE_MOCK) return mock.getDocument(id);
  return json(await fetch(`${BASE}/documents/${id}`));
}

export function documentPdfUrl(id: number): string {
  if (USE_MOCK) return mock.documentPdfUrl(id);
  return `${BASE}/documents/${id}/pdf`;
}

export async function getRoles(): Promise<RoleInfo[]> {
  if (USE_MOCK) return mock.getRoles();
  return json(await fetch(`${BASE}/obligations/roles`));
}

export async function getObligations(
  docId: number,
  role: string | null,
  groupBy: string
): Promise<ObligationGroups> {
  if (USE_MOCK) return mock.getObligations(docId, role, groupBy);
  const params = new URLSearchParams({ group_by: groupBy });
  if (role) params.set("role", role);
  return json(await fetch(`${BASE}/obligations/document/${docId}?${params}`));
}

export async function updateObligationStatus(id: number, status: string): Promise<void> {
  if (USE_MOCK) return mock.updateObligationStatus(id, status);
  await json(await fetch(`${BASE}/obligations/${id}?status=${status}`, { method: "PATCH" }));
}
