"use client";

// Upload entry point. Orchestrates the security flow:
// pick file → POST /documents/scan → (PII? show modal) → POST /documents.

import { useRef, useState } from "react";
import { scanDocument, uploadDocument } from "@/lib/api";
import type { PiiFinding } from "@/lib/types";
import PiiModal from "./PiiModal";

interface Props {
  onUploaded: (docId: number) => void;
}

export default function UploadZone({ onUploaded }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [findings, setFindings] = useState<PiiFinding[]>([]);

  async function handleFile(file: File) {
    setError(null);
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
      setError(String(e));
      setBusy(null);
    }
  }

  async function doUpload(file: File, acknowledged: boolean) {
    setBusy("Uploading and reading the document…");
    try {
      const res = await uploadDocument(file, acknowledged);
      onUploaded(res.id);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const f = e.dataTransfer.files?.[0];
          if (f) void handleFile(f);
        }}
        className="cursor-pointer border border-dashed border-[#16324f]/40 bg-white p-10 text-center hover:border-[#16324f]"
      >
        <p className="text-sm font-medium text-[#16324f]">
          Drop a federal contract or solicitation PDF here
        </p>
        <p className="mt-1 text-xs text-[#51606f]">
          or click to browse · PDF only · auto-deleted after 3 days
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void handleFile(f);
          }}
        />
      </div>

      {busy && <p className="mt-3 text-sm text-[#51606f]">{busy}</p>}
      {error && <p className="mt-3 text-sm text-red-800">{error}</p>}

      {pendingFile && (
        <PiiModal
          findings={findings}
          onCancel={() => {
            setPendingFile(null);
            setFindings([]);
          }}
          onConfirm={() => {
            const f = pendingFile;
            setPendingFile(null);
            setFindings([]);
            if (f) void doUpload(f, true); // explicit acknowledgment recorded
          }}
        />
      )}
    </div>
  );
}
