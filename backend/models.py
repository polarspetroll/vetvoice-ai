from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, Float, Boolean, Text, JSON, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # E.164
    email: Mapped[str | None] = mapped_column(String(120))
    pets: Mapped[list["Pet"]] = relationship(back_populates="owner")


class Pet(Base):
    __tablename__ = "pets"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    species: Mapped[str] = mapped_column(String(30))
    breed: Mapped[str | None] = mapped_column(String(60))
    birth_year: Mapped[int | None] = mapped_column(Integer)
    owner: Mapped[Client] = relationship(back_populates="pets")


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey("pets.id"), index=True)
    vet: Mapped[str] = mapped_column(String(40))
    service: Mapped[str] = mapped_column(String(60))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default="booked")  # booked / cancelled
    gcal_event_id: Mapped[str | None] = mapped_column(String(200))
    call_id: Mapped[int | None] = mapped_column(ForeignKey("calls.id"))  # call that last changed it
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    pet: Mapped[Pet] = relationship()

    # db level guard, a vet cant have 2 booked appts in the same slot
    __table_args__ = (
        Index("one_booking_per_vet_slot", "vet", "start_at", unique=True, postgresql_where=text("status = 'booked'"),
              sqlite_where=text("status = 'booked'")),
    )


class Call(Base):
    __tablename__ = "calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    room: Mapped[str] = mapped_column(String(120), index=True)
    caller_phone: Mapped[str | None] = mapped_column(String(20))
    sip_identity: Mapped[str | None] = mapped_column(String(120))
    scenario_id: Mapped[str | None] = mapped_column(String(20), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transferred: Mapped[bool] = mapped_column(Boolean, default=False)
    transfer_reason: Mapped[str | None] = mapped_column(String(200))
    transcript: Mapped[list | None] = mapped_column(JSON)
    usage: Mapped[dict | None] = mapped_column(JSON)  # tokens, audio seconds, chars


class TurnMetric(Base):
    __tablename__ = "turn_metrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), index=True)
    turn: Mapped[int] = mapped_column(Integer)
    eou_delay_ms: Mapped[float | None] = mapped_column(Float)
    llm_ttft_ms: Mapped[float | None] = mapped_column(Float)
    tts_ttfb_ms: Mapped[float | None] = mapped_column(Float)
    v2v_ms: Mapped[float | None] = mapped_column(Float)
    had_tool_call: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# not in the original spec but eval needs proof an sms went out
class SmsMessage(Base):
    __tablename__ = "sms_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int | None] = mapped_column(ForeignKey("calls.id"), index=True)
    to_phone: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))  # sent / dry_run / failed
    twilio_sid: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
