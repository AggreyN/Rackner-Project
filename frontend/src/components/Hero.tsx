// A reusable "hero" block: a badge, a big title, and a subtitle.
// It takes its text as PROPS, so the same component can show different
// content wherever we use it.

// 1. Describe the props this component accepts (TypeScript types).
type HeroProps = {
  badge: string;
  title: string;
  subtitle: string;
};

// 2. The component itself — a function that receives props and returns JSX.
//    `{ badge, title, subtitle }` pulls those three values out of the props.
export function Hero({ badge, title, subtitle }: HeroProps) {
  return (
    <div className="flex flex-col items-center text-center">
      <span className="mb-4 rounded-full border border-zinc-300 px-3 py-1 text-xs font-medium uppercase tracking-wide text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
        {badge}
      </span>
      <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50 sm:text-5xl">
        {title}
      </h1>
      <p className="mt-4 max-w-xl text-lg leading-8 text-zinc-600 dark:text-zinc-400">
        {subtitle}
      </p>
    </div>
  );
}
