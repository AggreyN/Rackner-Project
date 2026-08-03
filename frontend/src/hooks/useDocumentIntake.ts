"use client";

// The one intake flow, shared by the drop zone and the SAM.gov puller:
// validate → POST /documents/scan → (PII? wait for the modal decision)
// → POST /documents. Components stay presentational; this hook owns the
// security choreography.

import { useState } from "react";
import { scanDocument, uploadDocument } from "@/lib/api";
import type { PiiFinding } from "@/lib/types";

export const MAX_UPLOAD_MB = 25;

export function useDocumentIntake(onUploaded: (docId: number) => void) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [findings, setFindings] = useState<PiiFinding[]>([]);

  function validate(file: File): string | null {
    const isPdf =
      file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) {
      return "Only PDF files are supported — that's the format contracting offices publish.";
    }
    if (file.size === 0) {
      return "That file is empty (0 bytes). Re-download the document and try again.";
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      return `That file is ${(file.size / 1024 / 1024).toFixed(1)} MB — the limit is ${MAX_UPLOAD_MB} MB. Try splitting the document.`;
    }
    return null;
  }

  async function handleFile(file: File) {
    setError(null);
    const problem = validate(file);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy("Scanning for sensitive information…");
    try {
      const scan = await scanDocument(file);
      if (scan.has_pii) {
        setPendingFile(file);
        setFindings(scan.findings);
        setBusy(null);
        return; // wait for the user's decision in the modal
      }
      await doUpload(file, false);
    } catch (e) {
      setError(friendly(e));
      setBusy(null);
    }
  }

  async function doUpload(file: File, acknowledged: boolean) {
    setBusy("Uploading and reading the document…");
    try {
      const res = await uploadDocument(file, acknowledged);
      onUploaded(res.id);
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusy(null);
    }
  }

  function confirmPii() {
    const f = pendingFile;
    setPendingFile(null);
    setFindings([]);
    if (f) void doUpload(f, true); // explicit acknowledgment recorded
  }

  function cancelPii() {
    setPendingFile(null);
    setFindings([]);
  }

  return {
    busy,
    error,
    piiPending: pendingFile !== null,
    findings,
    handleFile,
    confirmPii,
    cancelPii,
  };
}

function friendly(e: unknown): string {
  const msg = String(e instanceof Error ? e.message : e);
  if (msg.includes("Failed to fetch") || msg.includes("NetworkError")) {
    return "Could not reach the backend. Check your connection (or NEXT_PUBLIC_API_URL) and try again.";
  }
  if (msg.startsWith("413")) {
    return `The server rejected the file as too large (limit ${MAX_UPLOAD_MB} MB).`;
  }
  return `Something went wrong: ${msg}`;
}
