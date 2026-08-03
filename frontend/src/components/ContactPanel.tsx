"use client";

// Contracting contact — "who do I talk to to win it?" Discovered email
// with verifier confidence, plus the Procurement Integrity Act flag when
// the solicitation is active (CAP compliance note: surface, don't
// auto-contact; a human stays in the loop).

import type { ContactResult } from "@/lib/types";

export default function ContactPanel({ contact }: { contact: ContactResult }) {
  const initials = contact.name
    .split(/\s+/)
    .filter((w) => /^[A-Z]/.test(w))
    .map((w) => w[0])
    .slice(0, 2)
    .join("");

  return (
    <div className="border border-[#d7dee6] bg-white p-4 sm:p-5" data-testid="contact-panel">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-[#51606f]">
        Contracting contact
      </h3>
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#16324f] text-xs font-bold text-white">
          {initials}
        </div>
        <div className="min-w-0">
          <b className="text-sm text-[#16324f]">{contact.name}</b>
          <div className="text-xs text-[#51606f]">
            {contact.title} · {contact.office}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-[#f5f7f9] px-2 py-1 font-mono text-[12.5px] text-[#16324f]">
              {contact.email}
            </span>
            <span className="text-[10.5px] text-[#1e7a46]">
              ✓ {Math.round(contact.confidence * 100)}% verified
            </span>
          </div>
        </div>
      </div>

      {contact.active_solicitation && (
        <div
          className="mt-3 rounded-md border border-[#eeddba] bg-[#fbf4e6] px-2.5 py-2 text-[11px] leading-relaxed text-[#9a6a1e]"
          data-testid="integrity-flag"
        >
          ⚠ Procurement Integrity: this is an <b>active solicitation</b>. Log the contact now;
          direct outreach is appropriate during sources-sought / pre-RFP windows or via the
          official Q&amp;A channel — not for backchanneling. Human review required.
        </div>
      )}
    </div>
  );
}
