"use client";

// Sign-in — step 1 of the FDI flow. Rackner placeholder account for the
// Phase-1 demo. The backend stores only bcrypt hashes and returns a JWT;
// this page just forwards credentials over TLS and keeps the token in
// sessionStorage. In mock mode any rackner.com email signs in.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";
import { isSignedIn, setSession } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isSignedIn()) router.replace("/");
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const { access_token } = await login(email, password);
      setSession(access_token, email.trim().toLowerCase());
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#16324f] p-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-[380px] rounded-lg bg-white p-8 shadow-[0_10px_40px_rgba(0,0,0,.25)]"
      >
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-lg bg-[#16324f] text-2xl font-bold text-white">
          ◆
        </div>
        <h1 className="text-xl font-semibold text-[#16324f]">Rackner FDI</h1>
        <p className="mb-5 text-[13px] text-[#51606f]">Federal Document Intelligence</p>

        <label htmlFor="email" className="mb-1 block text-xs text-[#51606f]">
          Work email
        </label>
        <input
          id="email"
          type="email"
          required
          autoComplete="email"
          placeholder="you@rackner.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-md border border-[#d7dee6] px-3 py-2.5 text-sm focus:border-[#16324f] focus:outline-none"
        />

        <label htmlFor="password" className="mb-1 mt-3 block text-xs text-[#51606f]">
          Password
        </label>
        <input
          id="password"
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-md border border-[#d7dee6] px-3 py-2.5 text-sm focus:border-[#16324f] focus:outline-none"
        />

        {error && <p className="mt-3 text-sm text-[#a3231f]">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="mt-5 w-full rounded-md bg-[#16324f] py-2.5 text-sm font-semibold text-white hover:bg-[#0f2438] disabled:opacity-60"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>

        <p className="mt-4 text-center text-[11.5px] leading-relaxed text-[#51606f]">
          🔒 Encrypted in transit · credentials stored as salted hashes · runs in an isolated
          container
        </p>
      </form>
    </main>
  );
}
