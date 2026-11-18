# Phone setup (Twilio → LiveKit)

1. **Buy a number** in the Twilio console, a Toronto local number (416 or 647).
2. **Create an Elastic SIP trunk** in Twilio (Elastic SIP Trunking → Trunks → Create).
   Under *Origination* add your LiveKit SIP URI, for example `sip:xxxx.sip.livekit.cloud`
   (LiveKit Cloud → Settings → SIP URI). Then attach the number to the trunk.
3. **Create the LiveKit side**: put `TWILIO_PHONE_NUMBER` in `.env` and run
   `uv run python -m scripts.setup_sip`. This makes an inbound trunk for the number and a
   dispatch rule that gives every call its own room (`call-...`) and sends the `vetvoice` agent into it.
4. **Transfers**: set `STAFF_PHONE`. The `transfer_to_staff` tool calls LiveKit's
   `TransferSIPParticipant`, which sends a SIP REFER to Twilio. Turn on
   *Call Transfer (SIP REFER)* on the Twilio trunk or the transfer will be rejected.
5. **SMS**: set `TWILIO_SMS_FROM` (a number with SMS turned on) and `SMS_DRY_RUN=0`.
   Leave it on `1` for the caller-bot runs, the seeded test numbers are fake 555-01xx numbers.

Call the number. You should see a `call-...` room in the LiveKit dashboard and a new row in `calls`.
