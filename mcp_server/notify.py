import os
import logging

log = logging.getLogger("notify")


def send_sms(to_phone: str, body: str) -> tuple[str, str | None]:
    """returns (status, twilio sid). SMS_DRY_RUN=1 skips twilio, used for the fake test numbers"""
    if os.getenv("SMS_DRY_RUN", "1") == "1" or not os.getenv("TWILIO_ACCOUNT_SID"):
        log.info("dry run sms to %s: %s", to_phone, body)
        return "dry_run", None
    from twilio.rest import Client
    tw = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    try:
        msg = tw.messages.create(to=to_phone, from_=os.environ["TWILIO_SMS_FROM"], body=body)
        return "sent", msg.sid
    except Exception as e:
        log.error("twilio failed: %s", e)
        return "failed", None


async def sip_transfer(room: str, identity: str) -> bool:
    """cold transfer the phone caller to the front desk number"""
    staff = os.getenv("STAFF_PHONE")
    if not (staff and identity and os.getenv("LIVEKIT_URL")):
        return False
    from livekit import api
    async with api.LiveKitAPI() as lk:
        await lk.sip.transfer_sip_participant(api.TransferSIPParticipantRequest(
            room_name=room, participant_identity=identity, transfer_to=f"tel:{staff}", play_dialtone=False))
    return True
