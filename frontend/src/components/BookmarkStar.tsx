"use client";

// The save/unsave toggle. Lives inside opportunity cards (which are links),
// so it must swallow the click — starring is not navigating.

import { toggleBookmark, useBookmarks } from "@/lib/bookmarks";

export default function BookmarkStar({ id, size = "sm" }: { id: string; size?: "sm" | "md" }) {
  const saved = useBookmarks().includes(id);
  return (
    <button
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        toggleBookmark(id);
      }}
      aria-pressed={saved}
      aria-label={saved ? "Remove from saved" : "Save opportunity"}
      title={saved ? "Remove from saved" : "Save opportunity"}
      data-testid="bookmark-star"
      className={
        (size === "md" ? "text-xl " : "text-base ") +
        "leading-none transition-colors " +
        (saved ? "text-[#9a6a1e] hover:text-[#7a5416]" : "text-[#c6cfd8] hover:text-[#9a6a1e]")
      }
    >
      {saved ? "★" : "☆"}
    </button>
  );
}
