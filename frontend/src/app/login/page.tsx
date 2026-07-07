"use client";

// Sign-in, shown only when the AUTH_ENABLED flag is on. Sessions are JWTs
// in sessionStorage (12h expiry server-side) — nothing persists on shared
// demo machines.

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";
import { isAuthEnabled, setToken } from "@/lib/auth";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isAuthEnabled()) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f5f7f9] p-6">
        <div className="max-w-md border border-[#d7dee6] bg-white p-6 text-center">
          <h1 className="text-base font-semibold text-[#16324f]">
            Authentication is switched off
          </h1>
          <p className="mt-2 text-sm text-[#51606f]">
            The demo runs frictionless with <code>NEXT_PUBLIC_AUTH_ENABLED</code> unset.
            Flip the flag (frontend and backend together) to exercise the login flow.
          </p>
          <Link
            href="/"
            className="mt-4 inline-block bg-[#16324f] px-4 py-2 text-sm text-white hover:bg-[#0f2438]"
          >
            Go to the app
          </Link>
        </div>
      </main>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await login(email, password);
      setToken(res.access_token);
      router.replace("/");
    } catch {
      setError("Sign-in failed — check the email and password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f5f7f9] p-6">
      <form onSubmit={submit} className="w-full max-w-sm border border-[#d7dee6] bg-white p-6">
        <h1 className="text-base font-semibold text-[#16324f]">
          Team Anvil — sign in
        </h1>
        <p className="mt-1 text-xs text-[#51606f]">
          Sessions expire after 12 hours. Passwords are never stored — bcrypt hashes only.
        </p>

        <label className="mt-4 block text-xs font-semibold text-[#51606f]" htmlFor="email">
          Email
        </label>
        <input
          id="email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1 w-full border border-[#d7dee6] px-3 py-2 text-sm text-[#16324f] focus:border-[#16324f] focus:outline-none"
        />

        <label className="mt-3 block text-xs font-semibold text-[#51606f]" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full border border-[#d7dee6] px-3 py-2 text-sm text-[#16324f] focus:border-[#16324f] focus:outline-none"
        />

        {error && (
          <p className="mt-3 text-sm text-[#9a6a1e]" role="alert">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="mt-5 w-full bg-[#16324f] px-4 py-2 text-sm text-white hover:bg-[#0f2438] disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
