"""The LLM gateway — the single seam between the backend and the model.

Two public functions:

    extract_obligations(sections)                      -> list[Obligation dict]
    analyze(opportunity, lifecycle_profile, sections)  -> Analysis dict

Both route to Bedrock (LLM_MODE=bedrock) or the mock (default) and then run the
shared assembly: normalize to SCHEMA_v2, attach a citation naming the section
the quote came from, apply the no-hallucination check, and — for analyze —
derive `score`, `band` and `verdict` on the backend. The model is never trusted
to compute the score or to declare its own quote verified.

Extraction is done PER SECTION rather than over one concatenated blob. That is
what makes `citation.section` truthful: an obligation's quote is verified
against the exact section its citation names, so the UI's
`section.text.indexOf(quote)` is guaranteed to succeed when verified=True.
"""

import json
import logging
import re

from app import config
from app.llm import mock, prompts
from app.llm.verify import realign_quote, verify_quote
from app.schemas import FitFactor, band_for, compatibility_score, verdict_for

# Schema defaults so a sparse model response still produces a valid Obligation.
_OBLIGATION_DEFAULTS = {
    "text": "",
    "obligation_type": "",
    "time_bucket": "unclear",
    "deadline_label": "",
    "verbatim_quote": "",
}

_VALID_TIME_BUCKETS = {
    "immediate",
    "30_days",
    "at_award",
    "quarterly",
    "ongoing",
    "unclear",
}


def _parse_json(text: str):
    """Best-effort JSON parse of a model response (tolerates ``` fences / prose)."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1 :] if "\n" in text else text
    try:
        return json.loads(text)
    except Exception:
        for open_c, close_c in (("[", "]"), ("{", "}")):
            i, j = text.find(open_c), text.rfind(close_c)
            if i != -1 and j != -1 and j > i:
                try:
                    return json.loads(text[i : j + 1])
                except Exception:
                    continue
        return []


def _section_field(section, name: str, default=""):
    """Sections may arrive as ORM rows or plain dicts."""
    if isinstance(section, dict):
        return section.get(name, default)
    return getattr(section, name, default)


def _normalize_obligation(raw: dict, *, ob_id: int, section) -> dict:
    ob = dict(_OBLIGATION_DEFAULTS)
    for k in _OBLIGATION_DEFAULTS:
        if raw.get(k) is not None:
            ob[k] = raw[k]
    if ob["time_bucket"] not in _VALID_TIME_BUCKETS:
        ob["time_bucket"] = "unclear"

    ref = _section_field(section, "ref", "") or ""
    ob["id"] = ob_id
    # Citation names THIS section — the one the quote was verified against.
    # Refs are stored without the "§" prefix (SCHEMA_v2).
    ob["citation"] = {
        "section": ref.lstrip("§").strip(),
        "page": _section_field(section, "page", None),
    }

    section_text = _section_field(section, "text", "") or ""

    # Repair before judging. The model reliably identifies the right passage but
    # re-wraps whitespace across line breaks, which fails an exact match. If the
    # quote can be placed unambiguously, swap in the source's own text for that
    # span; otherwise leave the model's text untouched so the UI can show it as
    # unconfirmed. Realignment never invents a quote — see verify.realign_quote.
    repaired = realign_quote(ob["verbatim_quote"], section_text)
    if repaired is not None:
        ob["verbatim_quote"] = repaired

    # Set by code against the exact served text, never by the model. Still an
    # exact substring test — realignment changes the quote, never the standard.
    ob["verified"] = verify_quote(ob["verbatim_quote"], section_text)
    return ob


def _raw_obligations_for(section_text: str) -> list[dict]:
    if config.LLM_MODE == "bedrock":
        from app.llm import bedrock_client

        parsed = _parse_json(
            bedrock_client.invoke(
                prompts.EXTRACT_SYSTEM, prompts.extract_user_prompt(section_text)
            )
        )
        if isinstance(parsed, list):
            return parsed
        return parsed.get("obligations", []) if isinstance(parsed, dict) else []
    return mock.extract(section_text)


def extract_obligations(sections: list) -> list[dict]:
    """Extract obligations from each section, cited and verified against it.

    Unverified quotes are kept with verified=False — never dropped.

    In bedrock mode the per-section model calls run CONCURRENTLY, bounded by
    LLM_EXTRACT_CONCURRENCY. Sequential, a 60-section package took minutes
    and outlived every load-balancer timeout (measured in prod); 8-wide it
    fits inside one request. Results are assembled in section order after all
    calls return, so the output — ids included — is identical to what the
    sequential path produced.
    """
    sections = list(sections or [])
    # Cost guard for bedrock mode: one model call per section. Never silent —
    # the log says exactly what was skipped (ground rule: no silent caps).
    if config.LLM_MODE == "bedrock" and len(sections) > config.LLM_MAX_EXTRACT_SECTIONS:
        logging.getLogger(__name__).warning(
            "extraction capped at %d of %d sections (LLM_MAX_EXTRACT_SECTIONS)",
            config.LLM_MAX_EXTRACT_SECTIONS,
            len(sections),
        )
        sections = sections[: config.LLM_MAX_EXTRACT_SECTIONS]

    worked = [
        s for s in sections if (_section_field(s, "text", "") or "").strip()
    ]
    # Extract plain strings BEFORE the fan-out: worker threads must never
    # touch ORM rows (a lazy-load on a shared Session from 8 threads is a
    # race, even if today's attribute access happens to be a cached read).
    texts = [(_section_field(s, "text", "") or "") for s in worked]
    workers = min(config.LLM_EXTRACT_CONCURRENCY, len(worked)) or 1
    raw_lists = _extract_raw_lists(texts, workers)

    obligations: list[dict] = []
    next_id = 1
    for section, raws in zip(worked, raw_lists):
        for raw in raws:
            obligations.append(
                _normalize_obligation(raw, ob_id=next_id, section=section)
            )
            next_id += 1
    return obligations


def _extract_raw_lists(texts: list[str], workers: int) -> list[list[dict]]:
    """Run per-section extraction, degrading per SECTION, not per run.

    All-or-nothing at 60 sections was measured fatal in prod: one throttled
    call vaporized the whole multi-minute run, every retry re-failed the
    same way, and nothing ever cached. Instead: fan out (bedrock mode),
    retry each failed section once serially (throttles recover given a
    beat), then SKIP stragglers with a warning — fewer obligations beats no
    analysis, the same trade OCR already makes. If every section failed,
    raise: persisting an empty result would freeze it.
    """
    log = logging.getLogger(__name__)

    def safe(text: str):
        try:
            return _raw_obligations_for(text)
        except Exception as exc:  # noqa: BLE001 — degrade per section
            return exc

    if config.LLM_MODE == "bedrock" and workers > 1 and len(texts) > 1:
        from concurrent.futures import ThreadPoolExecutor

        # The bedrock client is a single shared instance built under a lock
        # (clients are thread-safe; racing their CREATION is not). pool.map
        # preserves input order.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(safe, texts))
    else:
        results = [safe(t) for t in texts]

    failures = [i for i, r in enumerate(results) if isinstance(r, Exception)]
    for i in failures:
        results[i] = safe(texts[i])  # one serial retry per failed section

    still_failed = [i for i, r in enumerate(results) if isinstance(r, Exception)]
    if still_failed and len(still_failed) == len(texts):
        raise results[still_failed[0]]  # total outage — nothing to ground
    for i in still_failed:
        log.warning(
            "extraction skipped section %d of %d after retry: %s",
            i + 1,
            len(texts),
            results[i],
        )
        results[i] = []
    return results


def _normalize_factor(raw: dict) -> dict | None:
    """Coerce a model factor into a FitFactor, or drop it if unusable."""
    try:
        return FitFactor(**raw).model_dump()
    except Exception:
        return None


def _score(factors: list[dict]) -> float:
    valid = [FitFactor(**f) for f in factors if _normalize_factor(f) is not None]
    return compatibility_score(valid) if valid else 0.0


def analyze(opportunity: dict, lifecycle_profile: dict, sections: list) -> dict:
    """Produce a full SCHEMA_v2 Analysis.

    The model supplies the factor scores and rationales; obligations come from
    the grounded per-section extraction; the backend derives score/band/verdict.
    """
    if config.LLM_MODE == "bedrock":
        from app.llm import bedrock_client

        parsed = _parse_json(
            bedrock_client.invoke(
                prompts.ANALYZE_SYSTEM,
                prompts.analyze_user_prompt(opportunity, lifecycle_profile),
            )
        )
        parsed = parsed if isinstance(parsed, dict) else {}
        raw_factors = parsed.get("factors", [])
        verdict_note = parsed.get("verdict", "") or parsed.get("summary", "")
    else:
        result = mock.analyze_factors(opportunity, lifecycle_profile)
        raw_factors = result["factors"]
        verdict_note = result["verdict_note"]

    factors = [f for f in (_normalize_factor(r) for r in raw_factors) if f]
    obligations = extract_obligations(sections)
    score = _score(factors)

    return {
        "opportunity_id": opportunity.get("id"),
        "score": score,
        "band": band_for(score),
        # `verdict` is prose in v2; prefer the model's line, else a derived one.
        "verdict": verdict_note or verdict_for(score),
        "factors": factors,
        "obligations": obligations,
    }


# Tolerates an UNTERMINATED string — that is the truncation case.
_ANSWER_RE = re.compile(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)')


def _salvage_answer(raw: str) -> str:
    """Recover the answer text from a response that failed JSON parsing.

    The model writes `answer` before `citations`, so when the output-token cap
    truncates the JSON mid-citation the answer text usually survives. Pull it
    out; if even that fails, return an explicit apology — never empty. Blank
    200s were shipped to real users before this existed.
    """
    match = _ANSWER_RE.search(raw or "")
    if match:
        fragment = match.group(1).rstrip("\\")
        try:
            return json.loads(f'"{fragment}"')
        except ValueError:
            text = fragment.replace("\\n", "\n").replace('\\"', '"')
            if text.strip():
                return text
    return (
        "I had trouble composing that answer — please ask again, or make the "
        "question more specific."
    )


def _chat_sections(question: str, sections: list) -> list:
    """Fit the grounding context into a budget on monster documents.

    Chat resends section text with every question; a full solicitation package
    runs to hundreds of KB, which is slow, expensive, and pushes the model
    toward truncated output. Under the budget nothing changes. Over it, keep
    the sections most lexically relevant to the question (plus the opening
    section for framing), in document order — and say so in the log. Citations
    are unaffected: kept sections are real sections, and validation upstream
    runs against the full set.
    """
    budget = config.CHAT_MAX_SECTION_CHARS
    lengths = [len(_section_field(s, "text", "") or "") for s in sections]
    if sum(lengths) <= budget or not sections:
        return sections

    words = set(re.findall(r"[a-z0-9]{3,}", (question or "").lower()))
    scored = []
    for i, section in enumerate(sections):
        text = (_section_field(section, "text", "") or "").lower()
        scored.append((sum(text.count(w) for w in words), i))

    keep = {0}  # the opening section frames what the document IS
    used = lengths[0]
    for score, i in sorted(scored, key=lambda t: (-t[0], t[1])):
        if i in keep or used + lengths[i] > budget:
            continue
        keep.add(i)
        used += lengths[i]

    logging.getLogger(__name__).warning(
        "chat context capped: %d of %d sections (%d of %d chars)",
        len(keep),
        len(sections),
        used,
        sum(lengths),
    )
    return [s for i, s in enumerate(sections) if i in keep]


def answer_question(question: str, sections: list, history: list | None = None) -> dict:
    """Answer a question grounded in the solicitation's own sections.

    Returns SCHEMA_v2's ChatAnswer shape: {answer, citations[{section, page}]}.

    Citations are validated against the sections we actually passed in — a model
    that cites a section that doesn't exist has its citation dropped rather than
    returned. The answer text is kept either way, because "I couldn't find that"
    is a useful answer; a citation pointing at a nonexistent clause is not.
    """
    by_ref: dict[str, object] = {}
    for section in sections or []:
        ref = str(_section_field(section, "ref", "") or "").lstrip("§").strip()
        if ref:
            by_ref[ref] = section

    if config.LLM_MODE == "bedrock":
        from app.llm import bedrock_client

        raw = bedrock_client.invoke(
            prompts.CHAT_SYSTEM,
            prompts.chat_user_prompt(
                question, _chat_sections(question, list(sections or [])), history
            ),
            max_tokens=config.CHAT_MAX_TOKENS,
        )
        parsed = _parse_json(raw)
        parsed = parsed if isinstance(parsed, dict) else {}
        answer = str(parsed.get("answer", "") or "")
        raw_citations = parsed.get("citations") or []
        if not answer.strip():
            # A truncated/garbled response must never become a blank bubble.
            answer = _salvage_answer(raw)
            raw_citations = raw_citations or []
    else:
        result = mock.answer_question(question, sections, history)
        answer, raw_citations = result["answer"], result["citations"]

    citations = []
    for citation in raw_citations:
        if not isinstance(citation, dict):
            continue
        ref = str(citation.get("section", "") or "").lstrip("§").strip()
        if ref not in by_ref:
            continue  # invented section ref — drop it
        page = citation.get("page")
        if page is None:
            page = _section_field(by_ref[ref], "page", None)
        try:
            page = int(page) if page is not None else None
        except (TypeError, ValueError):
            page = None

        # Ground the citation exactly like an obligation: repair whitespace
        # drift against the section it names, then verify by exact substring.
        # The model's own "verified" claim (if any) is ignored.
        section_text = _section_field(by_ref[ref], "text", "") or ""
        quote = str(citation.get("verbatim_quote", "") or "")
        repaired = realign_quote(quote, section_text)
        if repaired is not None:
            quote = repaired
        citations.append(
            {
                "section": ref,
                "page": page,
                "verbatim_quote": quote,
                "verified": verify_quote(quote, section_text),
            }
        )

    return {"answer": answer, "citations": citations}
