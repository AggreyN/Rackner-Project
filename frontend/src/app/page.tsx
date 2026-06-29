export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center bg-zinc-50 px-6 text-center dark:bg-zinc-950">
      <span className="mb-4 rounded-full border border-zinc-300 px-3 py-1 text-xs font-medium uppercase tracking-wide text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
        Rackner AI Innovation Fellowship
      </span>
      <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50 sm:text-5xl">
        Contract Obligation Extractor
      </h1>
      <p className="mt-4 max-w-xl text-lg leading-8 text-zinc-600 dark:text-zinc-400">
        Turn a dense government contract into a plain-English, source-cited,
        deadline-aware obligation checklist.
      </p>
      <p className="mt-8 text-sm text-zinc-400 dark:text-zinc-500">
        Week 1 — foundation is live. The split-pane viewer is coming soon.
      </p>
    </main>
  );
}
