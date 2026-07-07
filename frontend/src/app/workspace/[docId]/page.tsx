"use client";

// The workspace: obligations & details on the left, source document on the
// right (collapsible) — modeled on Claude's dual view.

import { Suspense, use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import ObligationList from "@/components/ObligationList";
import DocumentPane from "@/components/DocumentPane";
import { documentPdfUrl, getDocument, getObligations, getRoles } from "@/lib/api";
import type { DocumentMeta, ObligationGroups, RoleInfo } from "@/lib/types";

// useSearchParams needs a Suspense boundary at build time.
export default function Workspace(props: { params: Promise<{ docId: string }> }) {
  return (
    <Suspense>
      <WorkspaceInner {...props} />
    </Suspense>
  );
}

function WorkspaceInner({ params }: { params: Promise<{ docId: string }> }) {
  const { docId: docIdStr } = use(params);
  const docId = Number(docIdStr);
  const search = useSearchParams();

  const [role, setRole] = useState<string | null>(search.get("role"));
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [doc, setDoc] = useState<DocumentMeta | null>(null);
  const [data, setData] = useState<ObligationGroups | null>(null);
  const [groupBy, setGroupBy] = useState("time");
  const [citePage, setCitePage] = useState<number | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    getRoles().then(setRoles).catch(() => {});
    getDocument(docId).then(setDoc).catch(() => {});
  }, [docId]);

  const refresh = useCallback(() => {
    getObligations(docId, role, groupBy).then(setData).catch(() => {});
  }, [docId, role, groupBy]);

  useEffect(refresh, [refresh]);

  const activeRole = roles.find((r) => r.key === role);

  return (
    <main className="flex h-screen flex-col bg-[#f5f7f9]">
      <header className="flex items-center justify-between border-b border-[#d7dee6] bg-white px-4 py-2">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-sm font-semibold text-[#16324f]">
            ← Team Anvil
          </Link>
          <span className="text-xs text-[#51606f]">
            {doc?.filename ?? `Document #${docId}`}
            {doc?.expires_at && (
              <> · auto-deletes {new Date(doc.expires_at).toLocaleDateString()}</>
            )}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-xs text-[#51606f]">Viewing as</label>
          <select
            value={role ?? ""}
            onChange={(e) => setRole(e.target.value || null)}
            className="border border-[#d7dee6] bg-white px-2 py-1 text-xs text-[#16324f]"
          >
            <option value="">All roles</option>
            {roles.map((r) => (
              <option key={r.key} value={r.key}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
      </header>

      {activeRole && (
        <div className="border-b border-[#d7dee6] bg-[#16324f] px-4 py-1.5 text-xs text-white/85">
          {activeRole.label}: {activeRole.question}
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <div className={collapsed ? "flex-1" : "w-[46%] min-w-[380px]"}>
          <ObligationList
            data={data}
            groupBy={groupBy}
            onGroupBy={setGroupBy}
            onCite={setCitePage}
          />
        </div>
        <DocumentPane
          pdfUrl={documentPdfUrl(docId)}
          page={citePage}
          collapsed={collapsed}
          onToggle={() => setCollapsed(!collapsed)}
        />
      </div>
    </main>
  );
}
