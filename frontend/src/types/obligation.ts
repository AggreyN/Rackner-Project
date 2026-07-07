// The shared shape of an "obligation" extracted from a contract.
// This is a DRAFT — confirm the final field names with Role 1 (Kaliza) and
// Aggrey in Week 3. The whole UI renders this shape, and Aggrey's real API
// will return it later (Week 8), so we all code to the same contract.

export type ObligationStatus = "pending" | "accepted" | "rejected";

export type Obligation = {
  id: string; // unique id for this obligation
  text: string; // plain-English obligation ("You must report ...")
  type: string; // category, e.g. "Reporting", "Deliverable", "Compliance"
  deadline: string | null; // trigger or due date, or null if none
  responsibleParty: string; // who is on the hook, e.g. "Contractor"
  sourceClauseId: string; // FAR/DFARS clause it came from, e.g. "252.204-7012"
  verbatimQuote: string; // exact source text (used to verify / highlight)
  page: number; // PDF page the quote is on (used for click-to-highlight)
  confidence: number; // model confidence, 0..1
  status: ObligationStatus; // review state
};
