"use client";

// Security requirement: if PII is detected pre-upload, the user must
// explicitly confirm before the file is stored. Flat navy/white, no gradients.

import type { PiiFinding } from "../lib/types";

interface Props {
  findings: PiiFinding[];
  onConfirm: () => void;
  onCancel: () => void;
}

export default function PiiModal({ findings, onConfirm, onCancel }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#16324f]/40">
      <div className="w-full max-w-md border border-[#d7dee6] bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-[#16324f]">
          Sensitive information detected
        </h2>
        <p className="mt-2 text-sm text-[#51606f]">
          This document appears to contain the following before upload. Are you
          sure you want to upload it? It will be stored for 3 days, then
          permanently deleted.
        </p>

        <ul className="mt-4 divide-y divide-[#d7dee6] border border-[#d7dee6]">
          {findings.map((f) => (
            <li key={f.kind} className="flex items-center justify-between px-3 py-2 text-sm">
              <span className="font-medium text-[#16324f]">{f.kind}</span>
              <span className="text-[#51606f]">
                {f.count}× &nbsp;·&nbsp; e.g. {f.sample}
              </span>
            </li>
          ))}
        </ul>

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="border border-[#d7dee6] px-4 py-2 text-sm text-[#16324f] hover:bg-[#f5f7f9]"
          >
            Cancel upload
          </button>
          <button
            onClick={onConfirm}
            className="bg-[#16324f] px-4 py-2 text-sm text-white hover:bg-[#0f2438]"
          >
            I understand — upload anyway
          </button>
        </div>
      </div>
    </div>
  );
}
