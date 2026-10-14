"""dev 管理员测试中心。请求只登记/查询任务，独立 worker 负责执行。"""

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user
from app.config.settings import settings
from app.services.test_center import TestCenter
from app.services.test_center_ai import get_context, list_contexts, save_context
from app.utils.super_admin import is_super_admin_user

router = APIRouter(prefix="/admin/test-center", tags=["Admin 测试中心"])


def get_center(current_user=Depends(get_current_user)) -> TestCenter:
    if not is_super_admin_user(current_user):
        raise HTTPException(403, "仅超级管理员可访问")
    if (
        settings.APP_ENV.lower() not in {"development", "dev", "test"}
        or os.environ.get("TEST_CENTER_ENABLED") != "1"
    ):
        raise HTTPException(404, "测试中心仅在 dev 显式开启")
    control = os.environ.get("TEST_CENTER_ROOT", "")
    if not control or not Path(control).is_absolute():
        raise HTTPException(503, "请配置独立的 TEST_CENTER_ROOT 绝对路径并启动 worker")
    return TestCenter(Path(__file__).resolve().parents[5], Path(control))


def response(call, *args, **kwargs):
    try:
        return {"code": 200, "message": "ok", "data": call(*args, **kwargs)}
    except KeyError as error:
        raise HTTPException(404, "用例、批次或证据不存在") from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


class Budget(BaseModel):
    max_calls: int = Field(ge=1, le=1000)
    max_tokens: int = Field(ge=1, le=20000000)


class RunRequest(BaseModel):
    case_ids: list[str] = Field(min_length=1, max_length=100)
    mode: Literal["diagnostic", "release"] = "diagnostic"
    budget: Budget | None = None


class CaseUpdate(BaseModel):
    core: bool
    archived: bool


class DraftRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    purpose: str | None = Field(default=None, max_length=4000)
    kind: Literal["api", "ui", "ai"]
    template_id: str | None = None
    case_id: str | None = None
    base_revision: str | None = None
    inputs: list[str] = Field(min_length=1, max_length=50)
    assertions: list[str] = Field(min_length=1, max_length=50)
    context_id: str | None = None
    repeats: int = Field(default=1, ge=1, le=10)
    conversation_mode: Literal["independent", "sequence", "workflow"] = "independent"


class SaveDraft(BaseModel):
    draft_id: str


@router.get("/drafts")
def drafts(center=Depends(get_center)):
    return response(center.authoring.drafts)


@router.post("/drafts")
def compile_draft(body: DraftRequest, center=Depends(get_center)):
    return response(center.authoring.compile, body.model_dump())


@router.post("/cases")
def save_draft(body: SaveDraft, center=Depends(get_center)):
    return response(center.authoring.save, body.draft_id)


@router.get("/cases/{case_id}/revisions")
def case_revisions(case_id: str, center=Depends(get_center)):
    return response(center.authoring.revisions, case_id)


@router.get("/catalog")
def catalog(center=Depends(get_center)):
    return response(center.catalog)


@router.get("/capabilities")
def capabilities(center=Depends(get_center)):
    from app.services.test_center_budget import capabilities as describe

    return response(describe, center)


@router.post("/contexts")
def create_context(body: dict, center=Depends(get_center)):
    return response(save_context, center, body)


@router.get("/contexts")
def contexts(center=Depends(get_center)):
    return response(list_contexts, center)


@router.get("/contexts/{context_id}")
def context_detail(context_id: str, center=Depends(get_center)):
    return response(get_context, center, context_id)


class ContextPreview(BaseModel):
    activation_code: str = Field(min_length=1, max_length=100)
    phase: Literal["values", "strengths", "interests", "purpose", "rumination"]
    thread_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=160)


@router.post("/contexts/preview")
def preview_context(body: ContextPreview, center=Depends(get_center)):
    from app.services.test_center_capture import preview

    return response(preview, body.model_dump())


@router.put("/cases/{case_id}")
def update_case(case_id: str, body: CaseUpdate, center=Depends(get_center)):
    return response(center.set_case, case_id, core=body.core, archived=body.archived)


@router.get("/runs")
def runs(center=Depends(get_center)):
    return response(center.list_runs)


@router.post("/runs", status_code=202)
def start_run(body: RunRequest, center=Depends(get_center)):
    return response(
        center.enqueue,
        body.case_ids,
        body.mode,
        body.budget.model_dump() if body.budget else None,
    )


class ReviewRequest(BaseModel):
    case_id: str
    attempt: int = Field(ge=0)
    verdict: Literal["pass", "fail", "needs_review"]
    reason: str = Field(min_length=1, max_length=4000)


@router.post("/runs/{run_id}/reviews")
def review_run(
    run_id: str,
    body: ReviewRequest,
    center=Depends(get_center),
    user=Depends(get_current_user),
):
    return response(
        center.authoring.review,
        run_id,
        body.model_dump(),
        str(user.get("user_id") or user.get("email")),
    )


@router.get("/runs/{run_id}")
def run_detail(run_id: str, center=Depends(get_center)):
    return response(center.get_run, run_id)


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, center=Depends(get_center)):
    return response(center.cancel, run_id)


@router.get("/runs/{run_id}/artifacts/{case_id}/{name}")
def artifact(run_id: str, case_id: str, name: str, center=Depends(get_center)):
    result = response(center.artifact, run_id, case_id, name)
    return FileResponse(result["data"], filename=name, media_type="application/octet-stream")
