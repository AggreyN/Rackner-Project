import { ObligationCard } from "@/components/ObligationCard";
import type { Obligation } from "@/types/obligation";
import mockObligations from "@/data/mock-obligations.json";

// Read the mock data and tell TypeScript it matches our Obligation shape.
const obligations = mockObligations as Obligation[];

export default function ReviewPage() {
  return (
    <div className="flex flex-1 flex-col md:flex-row">
      {/* LEFT: the PDF area (placeholder for now — real viewer comes in Slice 2) */}
      <section className="flex min-h-64 flex-1 items-center justify-center border-b border-zinc-200 bg-zinc-100 p-6 dark:border-zinc-800 dark:bg-zinc-900 md:border-b-0 md:border-r">
        <p className="text-sm text-zinc-400">
          📄 PDF viewer goes here (Slice 2)
        </p>
      </section>

      {/* RIGHT: the list of extracted obligations */}
      <section className="flex-1 overflow-y-auto p-6">
        <header className="mb-4">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            Obligations
          </h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {obligations.length} found · mock data
          </p>
        </header>

        {/* Render one ObligationCard per item in the list */}
        <div className="flex flex-col gap-3">
          {obligations.map((obligation) => (
            <ObligationCard key={obligation.id} obligation={obligation} />
          ))}
        </div>
      </section>
    </div>
  );
}
