"""second LiveKit agent that plays the caller in a test scenario.
run: python -m caller_bot.caller dev     the runner dispatches it into each test room"""
import os
import json
import random
import asyncio

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import AgentServer, AgentSession, Agent, JobContext, cli
from livekit.agents.beta.tools import EndCallTool
from livekit.agents.voice import room_io
from livekit.plugins import deepgram, anthropic, elevenlabs, silero

load_dotenv()

CALLER_PROMPT = """You are role playing a person phoning a vet clinic. Stay in character, never say you are an AI.
Talk like a normal person on the phone, short sentences. Only give details when asked or when it is natural.
Your goal: {goal}
When your goal is done or clearly can't be done, say bye and call end_call. If you are told you're being
transferred to staff, say okay and call end_call."""

INTERJECTIONS = ["sorry, sorry, go ahead", "wait, sorry", "uh, hang on", "yeah, sorry, I mean"]

server = AgentServer()


@server.rtc_session(agent_name="caller-bot")
async def entrypoint(ctx: JobContext):
    sc = json.loads(ctx.job.metadata)
    await ctx.connect()
    # the clinic agent is the only other agent in the room
    clinic = await ctx.wait_for_participant(kind=rtc.ParticipantKind.PARTICIPANT_KIND_AGENT)

    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=anthropic.LLM(model="claude-haiku-4-5", temperature=0.7),
        tts=elevenlabs.TTS(model="eleven_flash_v2_5", voice_id=os.getenv("CALLER_VOICE_ID", "pNInz6obpgDQGcFmaJgB")),
        vad=silero.VAD.load(),
    )

    # messy scenarios talk over the agent a couple of times
    if sc["category"] == "messy":
        left = {"n": 2}

        @session.on("user_state_changed")  # "user" here is the clinic agent
        def barge(ev):
            if ev.new_state == "speaking" and left["n"] > 0 and random.random() < 0.6:
                left["n"] -= 1

                async def later():
                    await asyncio.sleep(1.2)
                    session.say(random.choice(INTERJECTIONS), add_to_chat_ctx=True)
                asyncio.create_task(later())

    agent = Agent(instructions=CALLER_PROMPT.format(goal=sc["goal"]), tools=[EndCallTool(delete_room=True)])
    await session.start(agent=agent, room=ctx.room,
                        room_options=room_io.RoomOptions(participant_identity=clinic.identity))
    # dont speak first, a real caller waits for the greeting


if __name__ == "__main__":
    cli.run_app(server)
