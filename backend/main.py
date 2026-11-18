from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import Client, Pet, Call, TurnMetric

app = FastAPI(title="VetVoice backend")


class CallIn(BaseModel):
    room: str
    caller_phone: str | None = None
    sip_identity: str | None = None
    scenario_id: str | None = None


class CallEnd(BaseModel):
    transcript: list | None = None
    usage: dict | None = None


class TurnIn(BaseModel):
    call_id: int
    turn: int
    eou_delay_ms: float | None = None
    llm_ttft_ms: float | None = None
    tts_ttfb_ms: float | None = None
    v2v_ms: float | None = None
    had_tool_call: bool = False


def client_dict(c):
    return {"id": c.id, "first_name": c.first_name, "last_name": c.last_name, "phone": c.phone,
            "pets": [{"id": p.id, "name": p.name, "species": p.species, "breed": p.breed} for p in c.pets]}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/clients")
def get_clients(phone: str, db: Session = Depends(get_db)):
    rows = db.scalars(select(Client).where(Client.phone == phone)).all()
    return [client_dict(c) for c in rows]

@app.get("/pets")
def get_pets(client_id: int, db: Session = Depends(get_db)):
    pets = db.scalars(select(Pet).where(Pet.client_id == client_id)).all()
    return [{"id": p.id, "name": p.name, "species": p.species, "breed": p.breed, "birth_year": p.birth_year} for p in pets]


@app.post("/calls")
def create_call(body: CallIn, db: Session = Depends(get_db)):
    call = Call(**body.model_dump())
    db.add(call)

    db.commit()
    return {"id": call.id}


@app.post("/calls/{call_id}/end")
def end_call(call_id: int, body: CallEnd, db: Session = Depends(get_db)):
    call = db.get(Call, call_id)
    if not call:
        raise HTTPException(404, "call not found")
    call.ended_at = datetime.now(timezone.utc)
    call.transcript = body.transcript
    call.usage = body.usage
    db.commit()
    return {"ok": True}


@app.post("/turn_metrics")
def add_turn(body: TurnIn, db: Session = Depends(get_db)):
    db.add(TurnMetric(**body.model_dump()))
    db.commit()
    return {"ok": True}
