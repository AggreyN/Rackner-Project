"""Profile + lifecycle-plan upload.

    GET  /profile            -> Profile          (user from the JWT)
    POST /profile/lifecycle  -> LifecycleProfile (multipart PDF upload)

One active plan per user: re-uploading replaces the previous one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.deps import current_user, get_db
from app.models import FitEstimate
from app.models import LifecycleProfile as LifecycleProfileModel
from app.models import User
from app.schemas import LifecycleProfile, Profile
from app.schemas import User as UserSchema
from app.services import ingest, lifecycle_parse, storage

router = APIRouter(tags=["profile"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


def _user_schema(user: User) -> UserSchema:
    email = user.email or ""
    local, _, domain = email.partition("@")
    # "aggrey.narh" -> "AN"; falls back to the first letter.
    parts = [p for p in local.replace("_", ".").split(".") if p]
    initials = "".join(p[0] for p in parts[:2]).upper() or (email[:1].upper() or "?")
    return UserSchema(email=email, org=domain, initials=initials)


def _profile_schema(row: LifecycleProfileModel | None) -> LifecycleProfile | None:
    if row is None:
        return None
    return LifecycleProfile(
        filename=row.filename or "",
        uploaded_at=row.updated_at.isoformat() if row.updated_at else None,
        capabilities=row.capabilities or [],
        naics_codes=row.naics_codes or [],
        target_agencies=row.target_agencies or [],
        # DB column is `set_aside_status`; the v2 wire name is `set_asides`.
        set_asides=row.set_aside_status or [],
    )


def _current_plan(db: Session, user: User) -> LifecycleProfileModel | None:
    return db.scalar(
        select(LifecycleProfileModel)
        .where(LifecycleProfileModel.user_id == user.id)
        .order_by(LifecycleProfileModel.updated_at.desc())
    )


@router.get("/profile", response_model=Profile)
def get_profile(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> Profile:
    return Profile(
        user=_user_schema(user), lifecycle=_profile_schema(_current_plan(db, user))
    )


@router.post("/profile/lifecycle", response_model=LifecycleProfile)
async def upload_lifecycle_plan(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> LifecycleProfile:
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )

    filename = file.filename or "lifecycle-plan.pdf"
    text = ingest.load_text(data, filename)
    if not text.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "No text could be read from that file. If it is a scanned PDF, "
            "upload a text-based version.",
        )

    key = storage.put(data, filename=filename, prefix="lifecycle")
    parsed = lifecycle_parse.parse(text)

    row = _current_plan(db, user)
    if row is None:
        row = LifecycleProfileModel(user_id=user.id)
        db.add(row)

    row.filename = filename
    row.source_s3_key = key
    row.capabilities = parsed["capabilities"]
    row.naics_codes = parsed["naics_codes"]
    row.target_agencies = parsed["target_agencies"]
    row.set_aside_status = parsed["set_asides"]
    # Persisted for scoring; not serialized by the v2 wire type.
    row.past_performance = parsed["past_performance"]
    row.contract_vehicles = parsed["contract_vehicles"]
    row.size_min = parsed["size_min"]
    row.size_max = parsed["size_max"]

    # A new plan invalidates every cached pre-screen estimate: those scores
    # were computed against the OLD profile. (Full analyses stay — they are
    # regenerable verdicts keyed to opportunities, and far too expensive to
    # discard on every plan tweak.)
    db.query(FitEstimate).filter(FitEstimate.user_id == user.id).delete(
        synchronize_session=False
    )

    db.commit()
    db.refresh(row)
    return _profile_schema(row)
