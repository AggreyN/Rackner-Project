"""
WEEK 8 head start: a minimal FastAPI app.

Right now it just has a health check so you can confirm the server runs.
In Week 8 you'll add real endpoints (upload document, list obligations,
update review status) that read/write your Postgres tables.

Run it:
    uvicorn api.main:app --reload

Then open http://127.0.0.1:8000/docs  — FastAPI builds interactive docs for you.

Docs: https://fastapi.tiangolo.com/tutorial/
"""

from fastapi import FastAPI

app = FastAPI(title="Rackner Contract Obligation Extractor — API")


@app.get("/")
def health():
    return {"status": "ok", "service": "obligation-extractor"}


# WEEK 8 — you'll add endpoints like:
# @app.post("/documents")        -> upload + ingest a PDF
# @app.get("/documents/{id}/obligations")  -> list obligations with source spans
# @app.patch("/obligations/{id}")  -> accept / edit / reject (human-in-the-loop)
