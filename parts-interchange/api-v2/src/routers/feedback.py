from fastapi import APIRouter
from pydantic import BaseModel
from src.database import DbDep
from src.models.parts import Feedback

router = APIRouter(prefix="/v1", tags=["misc"])


class FeedbackIn(BaseModel):
    name: str | None = None
    email: str | None = None
    comments: str


@router.post("/feedback", status_code=201)
async def post_feedback(payload: FeedbackIn, db: DbDep):
    fb = Feedback(name=payload.name, email=payload.email, comments=payload.comments)
    db.add(fb)
    await db.commit()
    return {"ok": True}
