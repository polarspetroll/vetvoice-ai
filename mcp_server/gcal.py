"""google calendar sync with a service account. if env vars are missing it just does nothing
so the rest of the system still works locally"""
import os
import logging
from datetime import datetime

from mcp_server.scheduling import SLOT

log = logging.getLogger("gcal")
_service = None


def calendar_ids():
    return {"Dr. Patel": os.getenv("GCAL_DR_PATEL_ID"), "Dr. Chen": os.getenv("GCAL_DR_CHEN_ID")}


def enabled():
    return bool(os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")) and all(calendar_ids().values())


def service():
    global _service
    if _service is None:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"], scopes=["https://www.googleapis.com/auth/calendar"])
        _service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return _service


def _body(start: datetime, summary: str, appt_id: int):
    return {"summary": summary,
            "start": {"dateTime": start.isoformat(), "timeZone": "America/Toronto"},
            "end": {"dateTime": (start + SLOT).isoformat(), "timeZone": "America/Toronto"},
            "extendedProperties": {"private": {"appointment_id": str(appt_id)}}}


def create(vet, start, summary, appt_id):
    if not enabled():
        return None
    ev = service().events().insert(calendarId=calendar_ids()[vet], body=_body(start, summary, appt_id)).execute()
    return ev["id"]


def move(old_vet, new_vet, event_id, start, summary, appt_id):
    if not enabled() or not event_id:
        return event_id
    # moving between vets = delete + create, simpler than events().move
    if old_vet != new_vet:
        delete(old_vet, event_id)
        return create(new_vet, start, summary, appt_id)
    service().events().patch(calendarId=calendar_ids()[new_vet], eventId=event_id,
                             body=_body(start, summary, appt_id)).execute()
    return event_id


def delete(vet, event_id):
    if not enabled() or not event_id:
        return
    try:
        service().events().delete(calendarId=calendar_ids()[vet], eventId=event_id).execute()
    except Exception as e:  # already gone is fine
        log.warning("gcal delete failed %s", e)


def get(vet, event_id):
    if not enabled() or not event_id:
        return None
    return service().events().get(calendarId=calendar_ids()[vet], eventId=event_id).execute()
