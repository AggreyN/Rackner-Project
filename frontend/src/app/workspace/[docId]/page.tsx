"use client";

// The workspace: obligations & details on the left, source document on the
// right (collapsible) — modeled on Claude's dual view.
// Below lg the panes become a Register / Document toggle; citing an
// obligation flips to the document automatically.

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
  const [mobilePane, setMobilePane] = useState<"register" | "document">("register");

  useEffect(() => {
    getRoles().then(setRoles).catch(() => {});
    getDocument(docId).then(setDoc).catch(() => {});
  }, [docId]);

  const refresh = useCallback(() => {
    getObligations(docId, role, groupBy).then(setData).catch(() => {});
  }, [docId, role, groupBy]);

  useEffect(refresh, [refresh]);

  const cite = useCallback((page: number | null) => {
    setCitePage(page);
    if (page != null) setMobilePane("document"); // jump to the source on phones
  }, []);

  const activeRole = roles.find((r) => r.key === role);

  const registerClasses =
    (mobilePane === "register" ? "flex w-full " : "hidden ") +
    (collapsed ? "lg:flex lg:w-auto lg:flex-1" : "lg:flex lg:w-[46%] lg:min-w-[380px]");
  const documentClasses =
    (mobilePane === "document" ? "flex w-full " : "hidden ") +
    (collapsed ? "lg:flex lg:w-10 lg:shrink-0" : "lg:flex lg:flex-1 lg:min-w-0");

  return (
    <main className="flex h-dvh flex-col bg-[#f5f7f9]">
      <header className="flex items-center justify-between gap-3 border-b border-[#d7dee6] bg-white px-4 py-2">
        <div className="flex min-w-0 items-center gap-4">
          <Link href="/" className="shrink-0 text-sm font-semibold text-[#16324f]">
            ← Team Anvil
          </Link>
          <span className="hidden truncate text-xs text-[#51606f] sm:block">
            {doc?.filename ?? `Document #${docId}`}
            {doc?.expires_at && (
              <> · auto-deletes {new Date(doc.expires_at).toLocaleDateString()}</>
            )}
          </span>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <label htmlFor="role-switcher" className="hidden text-xs text-[#51606f] sm:block">
            Viewing as
          </label>
          <select
            id="role-switcher"
            value={role ?? ""}
            onChange={(e) => setRole(e.target.value || null)}
            className="max-w-44 border border-[#d7dee6] bg-white px-2 py-1 text-xs text-[#16324f]"
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
          <span className="font-semibold">{activeRole.label}</span>: {activeRole.question}
        </div>
      )}

      {/* Phone-width pane toggle — the split pane needs real estate */}
      <div className="flex border-b border-[#d7dee6] bg-white lg:hidden">
        {(["register", "document"] as const).map((p) => (
          <button
            key={p}
            onClick={() => setMobilePane(p)}
            className={
              "flex-1 py-2 text-xs font-semibold uppercase tracking-widest " +
              (mobilePane === p
                ? "border-b-2 border-[#16324f] text-[#16324f]"
                : "text-[#51606f]")
            }
          >
            {p === "register" ? "Register" : "Document"}
          </button>
        ))}
      </div>

      <div className="flex min-h-0 flex-1">
        <div className={registerClasses}>
          <ObligationList
            data={data}
            groupBy={groupBy}
            onGroupBy={setGroupBy}
            onCite={cite}
          />
        </div>
        <div className={documentClasses}>
          <DocumentPane
            pdfUrl={documentPdfUrl(docId)}
            page={citePage}
            collapsed={collapsed}
            onToggle={() => setCollapsed(!collapsed)}
          />
        </div>
      </div>
    </main>
  );
}
