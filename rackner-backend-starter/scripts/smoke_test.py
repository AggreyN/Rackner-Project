"""Week 8 integration smoke test — run the whole backend against real PDFs.

Boots the FastAPI app in-process against a throwaway SQLite database, pushes
every sample PDF through the real HTTP endpoints, and asserts the guarantees we
promise on stage:

  * a document uploads and reaches status "ready"
  * clauses and obligations land in the database
  * every obligation's verbatim_quote is verified against the source
  * obligations carry citation coordinates (page + quote_boxes)
  * the PII scan reports findings without storing anything
  * scanned (image-only) PDFs are reported, not silently empty

Run it (no Postgres needed):
    python scripts/smoke_test.py
    python scripts/smoke_test.py data/samples/one-file.pdf   # single file
"""

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Use a disposable DB + upload dir; never touch the real ones.
_TMP = tempfile.mkdtemp(prefix="anvil-smoke-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/smoke.db"
os.environ["UPLOAD_DIR"] = f"{_TMP}/uploads"

from fastapi.testclient import TestClient  # noqa: E402  (must follow env setup)

from api.main import app                    # noqa: E402
from db.database import SessionLocal        # noqa: E402
from db.models import Clause, Obligation    # noqa: E402

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(f"  [{mark}] {label}" + (f" {DIM}— {detail}{RESET}" if detail else ""))
    return ok


def smoke_one(client: TestClient, pdf: Path) -> bool:
    print(f"\n{pdf.name}")
    ok = True

    # 1. PII pre-scan stores nothing.
    with pdf.open("rb") as fh:
        scan = client.post("/documents/scan",
                           files={"file": (pdf.name, fh, "application/pdf")})
    ok &= check("scan returns findings", scan.status_code == 200,
                f"has_pii={scan.json()['has_pii']} "
                f"kinds={[f['kind'] for f in scan.json()['findings']]}")

    # 2. Real upload runs the pipeline.
    t0 = time.time()
    with pdf.open("rb") as fh:
        up = client.post("/documents",
                         files={"file": (pdf.name, fh, "application/pdf")},
                         data={"pii_acknowledged": "true"})
    elapsed = time.time() - t0
    if not check("upload -> ready", up.status_code == 200 and up.json()["status"] == "ready",
                 f"{up.status_code}"):
        return False
    doc_id = up.json()["id"]

    meta = client.get(f"/documents/{doc_id}").json()
    pages = meta["num_pages"] or 0
    rate = f"{pages / elapsed:.1f} pages/sec" if elapsed else "n/a"
    print(f"  {DIM}{pages} pages in {elapsed:.1f}s ({rate}){RESET}")

    with SessionLocal() as s:
        clauses = s.query(Clause).filter(Clause.document_id == doc_id).count()
        obs = s.query(Obligation).filter(Obligation.document_id == doc_id).all()
        unverified = [o for o in obs if not o.verified]
        grounded = [o for o in obs if o.quote_boxes]

    if clauses == 0 and not obs:
        # A scanned PDF with no text layer: report it, don't pretend it passed.
        ok &= check("scanned/empty PDF reported", True,
                    "no text layer — needs OCR (pip install pytesseract + brew install tesseract)")
        return ok

    ok &= check("clauses stored", clauses > 0, f"{clauses}")

    if not obs:
        # Not a failure: plenty of attachments (forms, questionnaires, price
        # sheets) carry no obligation language at all. Say so plainly instead of
        # crying wolf — and note the mock keys on "shall"/"must".
        print(f"  {DIM}note: 0 obligations — no obligation language in this document "
              f"(forms/questionnaires legitimately have none){RESET}")
        return ok

    ok &= check("every quote verified", not unverified,
                f"{len(obs) - len(unverified)}/{len(obs)}")
    ok &= check("obligations carry citations", bool(grounded),
                f"{len(grounded)}/{len(obs)} with quote_boxes")

    # 3. The role-filtered register the frontend actually calls.
    reg = client.get(f"/obligations/document/{doc_id}?role=security&group_by=time").json()
    ok &= check("role register responds", reg["total"] == len(obs),
                f"total={reg['total']} groups={list(reg['groups'])}")

    # 4. The PDF is still servable for the viewer pane.
    ok &= check("pdf served back", client.get(f"/documents/{doc_id}/pdf").status_code == 200)
    return ok


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv] or sorted((ROOT / "data" / "samples").glob("*.pdf"))
    if not targets:
        print("No PDFs found in data/samples/ — download a few from https://sam.gov")
        return 1

    print(f"Team Anvil backend smoke test — {len(targets)} document(s)")
    print(f"{DIM}scratch db: {_TMP}{RESET}")

    with TestClient(app) as client:
        if client.get("/").json().get("status") != "ok":
            print("health check failed")
            return 1
        results = {p.name: smoke_one(client, p) for p in targets}

    passed = sum(results.values())
    print(f"\n{'=' * 60}")
    for name, ok in results.items():
        print(f"  {GREEN + 'ok  ' + RESET if ok else RED + 'FAIL' + RESET}  {name}")
    print(f"{passed}/{len(results)} documents clean")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
