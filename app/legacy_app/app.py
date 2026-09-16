from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import uvicorn

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
app = FastAPI(title="Legacy Credit Union Demo")

MEMBERS = {
    "12345": {"name": "Alex Morgan", "checking": "$1,842.77", "savings": "$6,430.21", "status": "Active"},
    "24680": {"name": "Jordan Lee", "checking": "$920.10", "savings": "$12,005.00", "status": "Active"},
}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.post("/search", response_class=HTMLResponse)
def search(request: Request, member: str = Form(...)):
    if member == "00000":
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": "Permission denied for this member record."},
            status_code=200,
        )
    if member not in MEMBERS:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": "Member not found. Verify the member number and try again."},
            status_code=200,
        )
    return templates.TemplateResponse(
        request=request,
        name="member.html",
        context={"member_id": member, "member": MEMBERS[member]},
    )


@app.get("/member/{member_id}/subaccount", response_class=HTMLResponse)
def subaccount_form(request: Request, member_id: str):
    member = MEMBERS.get(member_id)
    if not member:
        return HTMLResponse("Member not found", status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="subaccount.html",
        context={"member_id": member_id, "member": member},
    )


@app.post("/member/{member_id}/subaccount/review", response_class=HTMLResponse)
def subaccount_review(request: Request, member_id: str, nickname: str = Form(...), deposit: str = Form(...)):
    member = MEMBERS.get(member_id)
    if not member:
        return HTMLResponse("Member not found", status_code=404)
    if not nickname.strip():
        return templates.TemplateResponse(
            request=request,
            name="subaccount.html",
            context={
                "member_id": member_id,
                "member": member,
                "error": "Validation error: nickname is required.",
            },
        )
    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context={"member_id": member_id, "member": member, "nickname": nickname, "deposit": deposit},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="warning")
