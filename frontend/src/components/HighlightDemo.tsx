// This component is INTERACTIVE (it responds to clicks), so it must run in the
// browser. In Next.js, that requires the "use client" line at the very top.
"use client";

import { useState } from "react";

export function HighlightDemo() {
  // useState gives this component a piece of "memory".
  //   highlighted     = the current value (starts as false)
  //   setHighlighted  = the function you call to change it
  const [highlighted, setHighlighted] = useState(false);

  return (
    <div className="mt-10 flex flex-col items-center gap-3">
      <p className="max-w-md text-zinc-700 dark:text-zinc-300">
        The contractor{" "}
        <span
          className={
            highlighted ? "rounded bg-yellow-200 px-1 text-zinc-900" : ""
          }
        >
          shall report any cyber incident within 72 hours
        </span>{" "}
        of discovery.
      </p>

      {/* onClick runs this function every time the button is clicked.
          It flips highlighted to the opposite of what it was. */}
      <button
        onClick={() => setHighlighted(!highlighted)}
        className="rounded-full bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
      >
        {highlighted ? "Clear highlight" : "Highlight the obligation"}
      </button>
    </div>
  );
}
