"use client";

// Landing: upload a document (drop zone or SAM.gov pull), pick your role,
// enter the workspace. Navy & white, flat surfaces, hairline borders.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import UploadZone from "@/components/UploadZone";
import RolePicker from "@/components/RolePicker";
import SamIntake from "@/components/SamIntake";
import PiiModal from "@/components/PiiModal";
import SignOutButton from "@/components/SignOutButton";
import { useDocumentIntake } from "@/hooks/useDocumentIntake";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { getRoles } from "@/lib/api";
import type { RoleInfo } from "@/lib/types";

export default function Home() {
  useRequireAuth();
  const router = useRouter();
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [rolesError, setRolesError] = useState(false);
  const [role, setRole] = useState<string | null>(null);
  const [docId, setDocId] = useState<number | null>(null);
  const intake = useDocumentIntake(setDocId);

  const loadRoles = () => {
    getRoles()
      .then((r) => {
        setRoles(r);
        setRolesError(false);
      })
      .catch(() => setRolesError(true));
  };
  useEffect(loadRoles, []);

  useEffect(() => {
    if (docId && role) router.push(`/workspace/${docId}?role=${role}`);
  }, [docId, role, router]);

  return (
    <main className="min-h-screen bg-[#f5f7f9]">
      <header className="border-b border-[#d7dee6] bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="text-base font-semibold text-[#16324f]">
              Team Anvil — Federal Document Intelligence
            </h1>
            <p className="text-xs text-[#51606f]">
              One document, read once. Every team gets its answers.
            </p>
          </div>
          <span className="flex items-center gap-3">
            <span className="hidden text-xs text-[#51606f] sm:block">
              Rackner AI Innovation Fellowship
            </span>
            <SignOutButton />
          </span>
        </div>
      </header>

      <div className="mx-auto max-w-5xl space-y-10 px-6 py-10">
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-[#51606f]">
            1 · Upload the document
          </h2>
          <UploadZone onFile={intake.handleFile} busy={intake.busy} error={intake.error} />
          {docId && (
            <p className="mt-2 text-sm text-[#1e7a46]">
              Document received — it&apos;s being read now. Choose your role below to open
              the workspace.
            </p>
          )}
        </section>

        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-[#51606f]">
            …or pull one straight from SAM.gov
          </h2>
          <SamIntake onFile={intake.handleFile} disabled={!!intake.busy} />
        </section>

        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-[#51606f]">
            2 · Choose your role
          </h2>
          <RolePicker roles={roles} selected={role} onSelect={setRole} />
          {rolesError && (
            <p className="mt-2 text-sm text-[#9a6a1e]">
              Couldn&apos;t load the role list.{" "}
              <button onClick={loadRoles} className="underline underline-offset-2">
                Retry
              </button>
            </p>
          )}
          {!docId && role && (
            <p className="mt-2 text-sm text-[#51606f]">
              Role selected — upload a document above to continue.
            </p>
          )}
        </section>

        <footer className="border-t border-[#d7dee6] pt-4 text-xs text-[#51606f]">
          Documents are scanned for sensitive information before upload and are
          permanently deleted after 3 days.
        </footer>
      </div>

      {intake.piiPending && (
        <PiiModal
          findings={intake.findings}
          onConfirm={intake.confirmPii}
          onCancel={intake.cancelPii}
        />
      )}
    </main>
  );
}
