"""Evidence REST API endpoints."""

from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.evidence import Evidence
from app.schemas.evidence import EvidenceResponse

router = APIRouter(prefix="/evidence", tags=["Evidence"])


def _resolve_safe_evidence_path(evidence: Evidence, base_dir: Path) -> Path:
    """Safely resolve an evidence file path and ensure strict containment within base_dir.

    Raises:
        HTTPException(403): If the resolved path escapes base_dir (path traversal attempt).
        HTTPException(404): If the file does not exist on disk.
    """
    raw_path = Path(evidence.file_path)
    if raw_path.is_absolute():
        resolved_path = raw_path.resolve()
    else:
        resolved_path = (base_dir / raw_path).resolve()

    # Directory containment verification
    try:
        resolved_path.relative_to(base_dir.resolve())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to the requested file path is forbidden.",
        )

    if not resolved_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence image file not found on disk.",
        )

    return resolved_path


@router.get(
    "/{evidence_id}",
    response_model=EvidenceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get evidence metadata",
    description="Retrieve evidence capture record metadata by external identifier or surrogate ID.",
)
def get_evidence_metadata(
    evidence_id: str,
    db: Session = Depends(get_db),
) -> EvidenceResponse:
    """Retrieve metadata for an evidence record."""
    stmt = select(Evidence).where(Evidence.evidence_id == evidence_id)
    evidence = db.scalar(stmt)

    if evidence is None and evidence_id.isdigit():
        evidence = db.scalar(select(Evidence).where(Evidence.id == int(evidence_id)))

    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence '{evidence_id}' not found.",
        )

    return EvidenceResponse.model_validate(evidence)


@router.get(
    "/{evidence_id}/file",
    response_class=FileResponse,
    status_code=status.HTTP_200_OK,
    summary="Download evidence image file",
    description="Retrieve the physical JPG evidence image frame with strict path containment security.",
)
def get_evidence_file(
    evidence_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Securely stream the physical evidence frame file."""
    stmt = select(Evidence).where(Evidence.evidence_id == evidence_id)
    evidence = db.scalar(stmt)

    if evidence is None and evidence_id.isdigit():
        evidence = db.scalar(select(Evidence).where(Evidence.id == int(evidence_id)))

    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence '{evidence_id}' not found.",
        )

    base_dir = Path(settings.evidence_dir).resolve()
    target_file = _resolve_safe_evidence_path(evidence, base_dir)

    return FileResponse(
        path=str(target_file),
        media_type="image/jpeg",
        filename=evidence.filename,
    )
