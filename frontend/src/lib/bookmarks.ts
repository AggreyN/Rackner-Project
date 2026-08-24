"use client";

// Saved opportunities, per user. Client-persisted in localStorage keyed by
// the signed-in email, so switching accounts switches lists (and signing in
// as someone else never leaks another user's saves on a shared machine).
//
// Saves live on the SERVER (they follow the user across devices and browsers):
//   GET    /profile/bookmarks          → string[] (opportunity ids)
//   PUT    /profile/bookmarks/{id}     → save
//   DELETE /profile/bookmarks/{id}     → unsave
// localStorage stays the synchronous read model — it is what renders, so a
// star reacts instantly — and it is the whole story in mock/offline mode.
// Writes go local-first then to the server, and revert if the server refuses.

import { useSyncExternalStore } from "react";
import { getEmail } from "./auth";
import { HAS_BACKEND, getBookmarks, removeBookmark, saveBookmark } from "./api";

const EVENT = "fdi-bookmarks-changed";

function storageKey(): string | null {
  const email = getEmail();
  return email ? `fdi_bookmarks::${email}` : null;
}

function read(): string[] {
  const key = storageKey();
  if (!key) return [];
  try {
    const raw = localStorage.getItem(key);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function write(ids: string[]): void {
  const key = storageKey();
  if (!key) return;
  localStorage.setItem(key, JSON.stringify(ids));
  window.dispatchEvent(new Event(EVENT));
}

export function toggleBookmark(id: string): void {
  const ids = read();
  const had = ids.includes(id);
  write(had ? ids.filter((x) => x !== id) : [...ids, id]);
  if (!HAS_BACKEND) return;
  const sync = had ? removeBookmark(id) : saveBookmark(id);
  sync.catch(() => {
    // The server refused (offline, expired session). Put the star back the
    // way it was rather than showing a save that did not happen.
    const now = read();
    write(had ? [...now, id] : now.filter((x) => x !== id));
  });
}

// --- server hydration -------------------------------------------------------

// Keyed by account, so signing in as someone else re-pulls THEIR list rather
// than reusing the first user's promise. (Keyed here rather than hooked into
// clearSession to avoid an auth -> bookmarks -> api -> auth import cycle.)
let hydratedFor: string | null = null;
let hydrating: Promise<void> | null = null;

/** Pull the signed-in user's saved list from the server once per account.
 *  Union, not replace: saves made in this browser before the server knew
 *  about them are kept and pushed up, so nothing a user starred disappears. */
export function hydrateBookmarks(): Promise<void> {
  const key = storageKey();
  if (!HAS_BACKEND || !key) return Promise.resolve();
  if (hydrating && hydratedFor === key) return hydrating;
  hydratedFor = key;
  hydrating = (async () => {
    try {
      const server = await getBookmarks();
      const local = read();
      const merged = Array.from(new Set([...server, ...local]));
      write(merged);
      await Promise.allSettled(
        local.filter((id) => !server.includes(id)).map((id) => saveBookmark(id))
      );
    } catch {
      // Offline or a dead session: localStorage keeps working on its own.
    }
  })();
  return hydrating;
}

export function isBookmarked(id: string): boolean {
  return read().includes(id);
}

// --- reactive subscription (shared across every component) ------------------

function subscribe(onChange: () => void): () => void {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange); // other tabs
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

// useSyncExternalStore needs a referentially-stable snapshot; cache the
// serialized form and only produce a new array when the contents change.
let cache: { raw: string; ids: string[] } = { raw: "[]", ids: [] };

function getSnapshot(): string[] {
  const ids = read();
  const raw = JSON.stringify(ids);
  if (raw !== cache.raw) cache = { raw, ids };
  return cache.ids;
}

/** Reactive list of the signed-in user's saved opportunity ids. */
export function useBookmarks(): string[] {
  return useSyncExternalStore(subscribe, getSnapshot, () => cache.ids);
}
