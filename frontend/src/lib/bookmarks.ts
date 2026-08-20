"use client";

// Saved opportunities, per user. Client-persisted in localStorage keyed by
// the signed-in email, so switching accounts switches lists (and signing in
// as someone else never leaks another user's saves on a shared machine).
//
// Backend seam: when the real API grows bookmark routes, this module is the
// one place to swap — expected shape:
//   GET    /profile/bookmarks          → string[] (opportunity ids)
//   PUT    /profile/bookmarks/{id}     → save
//   DELETE /profile/bookmarks/{id}     → unsave
// The store keeps localStorage as the offline/mock path either way.

import { useSyncExternalStore } from "react";
import { getEmail } from "./auth";

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
  write(ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]);
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
