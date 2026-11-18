"""VetVoice phone agent.  run: python -m agent.agent dev   (or `start` in prod)"""
import os
import json
import asyncio
import logging

import httpx
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import AgentServer, AgentSession, Agent, JobContext, JobProcess, cli, inference, mcp
from livekit.agents.beta.tools import EndCallTool
from livekit.agents.voice import room_io
from livekit.plugins import deepgram, anthropic, elevenlabs, silero

from agent.prompt import build_prompt, CLINIC

load_dotenv()
log = logging.getLogger("vetvoice")
BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")
MCP_URL = os.getenv("MCP_URL", "http://localhost:8001/mcp")
FILLER_AFTER = 1.0  # seconds, only speak a filler if a tool is slower than this


def ms(x):
    return round(x * 1000, 1) if x is not None else None

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server = AgentServer(setup_fnc=prewarm)


@server.rtc_session(agent_name="vetvoice")
async def entrypoint(ctx: JobContext):
    await ctx.connect()
    meta = json.loads(ctx.job.metadata or "{}")
    K = rtc.ParticipantKind
    caller = await ctx.wait_for_participant(kind=[K.PARTICIPANT_KIND_SIP, K.PARTICIPANT_KIND_STANDARD, K.PARTICIPANT_KIND_AGENT])
    is_sip = caller.kind == K.PARTICIPANT_KIND_SIP
    # real calls get the number from SIP, the test bot passes it in the dispatch metadata
    phone = caller.attributes.get("sip.phoneNumber") or meta.get("caller_phone")

    http = httpx.AsyncClient(base_url=BACKEND, timeout=5)
    # register the call and look up the caller before saying hi, saves a tool call later
    r = await http.post("/calls", json={"room": ctx.room.name, "caller_phone": phone,
                                        "sip_identity": caller.identity if is_sip else None,
                                        "scenario_id": meta.get("scenario_id")})
    call_id = r.json()["id"]

    client = None
    if phone:
        found = (await http.get("/clients", params={"phone": phone})).json()
        client = found[0] if found else None

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="en-US"),
        llm=anthropic.LLM(model="claude-haiku-4-5", temperature=0.3, caching="ephemeral"),
        tts=elevenlabs.TTS(model="eleven_flash_v2_5", voice_id=os.getenv("ELEVEN_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")),
        vad=ctx.proc.userdata["vad"],
        turn_handling={"turn_detection": inference.TurnDetector(),
                       "preemptive_generation": {"enabled": True}},
        mcp_servers=[mcp.MCPServerHTTP(url=MCP_URL, headers={"x-call-id": str(call_id)}, timeout=10,
                                       client_session_timeout_seconds=15)],
    )

    # ---- latency logging, one row per agent reply
    state = {"turn": 0, "user": {}, "tool": False}
    pending = set()

    def post_turn(m):
        state["turn"] += 1
        row = {"call_id": call_id, "turn": state["turn"],
               "eou_delay_ms": ms(state["user"].get("end_of_turn_delay")),
               "llm_ttft_ms": ms(m.get("llm_node_ttft")), "tts_ttfb_ms": ms(m.get("tts_node_ttfb")),
               "v2v_ms": ms(m.get("e2e_latency")), "had_tool_call": state["tool"]}
        state["tool"] = False
        t = asyncio.create_task(http.post("/turn_metrics", json=row))
        pending.add(t)
        t.add_done_callback(pending.discard)

    @session.on("conversation_item_added")
    def on_item(ev):
        item = ev.item
        if getattr(item, "type", None) != "message":
            return
        if item.role == "user":
            state["user"] = dict(item.metrics)
        elif item.role == "assistant" and item.metrics.get("e2e_latency") is not None:
            post_turn(item.metrics)

    # ---- spoken filler if a tool call takes > 1s
    timers = {}

    async def filler():
        await asyncio.sleep(FILLER_AFTER)
        session.say("One moment while I check.", add_to_chat_ctx=False, allow_interruptions=False)

    @session.on("tool_execution_updated")
    def on_tool(ev):
        u = ev.update
        if u.type == "tool_call_started":
            state["tool"] = True
            if u.function_call.name != "end_call":
                timers[u.function_call.call_id] = asyncio.create_task(filler())
        elif u.type == "tool_call_ended":
            t = timers.pop(u.call_id, None)
            if t:
                t.cancel()

    async def on_shutdown():
        transcript = [{"role": i.role, "text": i.text_content} for i in session.history.items
                      if getattr(i, "type", None) == "message" and i.text_content]
        usage = [u.model_dump() for u in session.usage.model_usage]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        try:
            await http.post(f"/calls/{call_id}/end", json={"transcript": transcript, "usage": {"models": usage}})
        finally:
            await http.aclose()

    ctx.add_shutdown_callback(on_shutdown)



    agent = Agent(instructions=build_prompt(client, phone), tools=[EndCallTool(delete_room=True)])
    await session.start(agent=agent, room=ctx.room,
                        room_options=room_io.RoomOptions(participant_identity=caller.identity))
    hello = f"Hi {client['first_name']}, thanks for calling {CLINIC}." if client else f"Thanks for calling {CLINIC}."
    # say() skips the llm so the greeting is instant
    session.say(hello + " How can I help you today?")


if __name__ == "__main__":
    cli.run_app(server)
