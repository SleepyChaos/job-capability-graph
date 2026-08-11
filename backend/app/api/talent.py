from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.talent.service import (
    TalentWorkflowError,
    answer_profile_question,
    create_learning_path,
    create_profile_draft,
    create_profile_version,
    get_profile,
    list_profiles,
    publish_profile,
    run_matching,
)

router = APIRouter(tags=["talent-matching"])


class ProfileDraftCreate(BaseModel):
    source_name: str = Field(min_length=1, max_length=500)
    mime_type: str = Field(default="text/plain", max_length=150)
    input_type_code: Literal["pasted_text", "txt", "docx_text", "pdf_text", "ocr_text"] = (
        "pasted_text"
    )
    content_text: str = Field(min_length=30, max_length=200_000)


class DialogueAnswer(BaseModel):
    answer_text: str = Field(min_length=1, max_length=5000)


class ProfileVersionCreate(BaseModel):
    target_role_text: str | None = Field(default=None, max_length=500)
    education_text: str | None = Field(default=None, max_length=500)
    experience_summary: str | None = Field(default=None, max_length=5000)


def _call(action):
    try:
        return action()
    except TalentWorkflowError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/talent/profiles", response_model=dict, status_code=201)
def create_profile(payload: ProfileDraftCreate, db: Annotated[Session, Depends(get_db)]):
    return _call(
        lambda: create_profile_draft(
            db,
            source_name=payload.source_name,
            mime_type=payload.mime_type,
            content_text=payload.content_text,
            input_type_code=payload.input_type_code,
        )
    )


@router.get("/talent/profiles", response_model=list[dict])
def get_profiles(db: Annotated[Session, Depends(get_db)]):
    return list_profiles(db)


@router.get("/talent/profiles/{version_code}", response_model=dict)
def get_profile_detail(version_code: str, db: Annotated[Session, Depends(get_db)]):
    return _call(lambda: get_profile(db, version_code=version_code))


@router.post("/talent/profiles/{version_code}/answers", response_model=dict)
def answer_question(
    version_code: str,
    payload: DialogueAnswer,
    db: Annotated[Session, Depends(get_db)],
):
    return _call(
        lambda: answer_profile_question(
            db, version_code=version_code, answer_text=payload.answer_text
        )
    )


@router.post("/talent/profiles/{version_code}/publish", response_model=dict)
def confirm_profile(version_code: str, db: Annotated[Session, Depends(get_db)]):
    return _call(lambda: publish_profile(db, version_code=version_code))


@router.post("/talent/profiles/{version_code}/versions", response_model=dict, status_code=201)
def make_profile_version(
    version_code: str,
    payload: ProfileVersionCreate,
    db: Annotated[Session, Depends(get_db)],
):
    return _call(
        lambda: create_profile_version(
            db,
            version_code=version_code,
            target_role_text=payload.target_role_text,
            education_text=payload.education_text,
            experience_summary=payload.experience_summary,
        )
    )


@router.post("/talent/profiles/{version_code}/matches", response_model=dict, status_code=201)
def match_profile(
    version_code: str,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
):
    return _call(lambda: run_matching(db, version_code=version_code, limit=limit))


@router.post("/talent/matches/{result_code}/learning-path", response_model=dict, status_code=201)
def build_learning_path(result_code: str, db: Annotated[Session, Depends(get_db)]):
    return _call(lambda: create_learning_path(db, result_code=result_code))
