"""
Audit log router — retrieve entries and generate the PDF report.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from services.session_manager import session_manager
from services.audit_logger import AuditLogger
from services.pdf_generator import generate_pdf

router = APIRouter()


def _get_session_or_404(session_id: str):
    s = session_manager.get(session_id)
    if s is None:
        raise HTTPException(404, f"Session {session_id} not found.")
    return s


@router.get("/{session_id}")
def get_audit_log(session_id: str):
    s = _get_session_or_404(session_id)
    if not s.audit_db.exists():
        return {"entries": []}
    logger = AuditLogger(s.audit_db, session_id)
    return {"entries": logger.get_all()}


@router.get("/{session_id}/report")
def download_report(
    session_id: str,
    case_number: str = "",
    analyst_name: str = "",
):
    s = _get_session_or_404(session_id)
    entries = []
    if s.audit_db.exists():
        entries = AuditLogger(s.audit_db, session_id).get_all()

    pdf_bytes = generate_pdf(s.meta, entries, case_number, analyst_name)
    filename = f"forensiccloud_report_{session_id[:8]}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class NotesRequest(BaseModel):
    entry_id: int
    notes: str


@router.post("/{session_id}/notes")
def add_notes(session_id: str, req: NotesRequest):
    s = _get_session_or_404(session_id)
    if not s.audit_db.exists():
        raise HTTPException(404, "No audit log for this session.")
    AuditLogger(s.audit_db, session_id).add_notes(req.entry_id, req.notes)
    return {"ok": True}
