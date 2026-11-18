"""creates the LiveKit inbound SIP trunk + dispatch rule for the Twilio Toronto number. run once.
the Twilio side (Elastic SIP trunk -> origination URI = your LiveKit SIP uri) is done in the console, see docs/telephony.md"""
import os
import asyncio

from dotenv import load_dotenv
from livekit import api

load_dotenv()


async def main():
    number = os.environ["TWILIO_PHONE_NUMBER"]  # like +14165550000
    async with api.LiveKitAPI() as lk:
        trunk = await lk.sip.create_inbound_trunk(api.CreateSIPInboundTrunkRequest(
            trunk=api.SIPInboundTrunkInfo(name="vetvoice-twilio", numbers=[number], krisp_enabled=True)))
        print("inbound trunk:", trunk.sip_trunk_id)

        rule = await lk.sip.create_dispatch_rule(api.CreateSIPDispatchRuleRequest(
            name="vetvoice-calls",
            trunk_ids=[trunk.sip_trunk_id],
            # every call gets its own room, and the vetvoice agent is sent into it
            rule=api.SIPDispatchRule(dispatch_rule_individual=api.SIPDispatchRuleIndividual(room_prefix="call-")),
            room_config=api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name="vetvoice")]),
        ))
        print("dispatch rule:", rule.sip_dispatch_rule_id)


if __name__ == "__main__":
    asyncio.run(main())
