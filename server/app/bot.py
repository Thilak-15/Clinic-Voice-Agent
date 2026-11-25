"""The voice pipeline.

    browser mic --WebRTC--> Silero VAD --> ElevenLabs STT --> Gemini (+ tools)
        --> ElevenLabs TTS --WebRTC--> browser speaker

One `run_bot` call handles one phone call (one WebRTC connection).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    AssistantTurnStoppedMessage,
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
    UserTurnStoppedMessage,
)
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from . import config, db, events, tools


def system_prompt() -> str:
    today = db.now().date()
    week = "\n".join(
        f"- {(today + timedelta(days=i)).strftime('%A %d %B %Y')} = "
        f"{(today + timedelta(days=i)).isoformat()}"
        for i in range(8)
    )
    doctors = "\n".join(f"- {d['name']}, {d['specialty']}" for d in db.list_doctors())
    return f"""You are {config.AGENT_NAME}, the phone receptionist at {config.CLINIC_NAME}.
You are on a live voice call. Everything you write is spoken aloud by a text-to-speech voice.

How to speak
- Short, warm, natural sentences. One question at a time. Usually one or two sentences.
- No lists, markdown, emojis or symbols. Say times like "ten thirty in the morning".
- When offering slots, offer two or three, not all of them.
- Don't mention tools, functions, JSON or IDs. Speak like a person.

What you can do
- Check a doctor's availability, book an appointment, cancel an appointment.
- For anything else (medical advice, prescriptions, billing), say you can only help with
  appointments and suggest they speak with the front desk. In an emergency, tell them to call 112.

Caller identity
- The caller is identified only by the mobile number they say on this call.
- Before booking or cancelling, ask for their 10-digit mobile number if you don't have it.
- Read it back digit by digit in two groups of five, for example
  "nine eight seven six five, four three two one zero. Is that right?"
- Only after a clear yes, call the tool with phone_confirmed set to true.
  If they correct you, read the corrected number back again.
- Pass phone numbers to tools as 10 digits only.

Booking
- Work out the doctor (or speciality), the day, then the time. Always check availability
  before offering times; never invent slots.
- Once the caller picks a time, ALWAYS ask "May I have the patient's name?" before you
  ask for the phone number. Pass it as patient_name. Only skip it if they refuse.
- After booking, confirm doctor, day and time, and give the 4-digit reference.

Cancelling
- Use the confirmed phone number. If there are several appointments, describe them briefly
  and ask which one. Confirm the cancellation out loud.

Dates (today is the first line; use these exact YYYY-MM-DD values in tool calls)
{week}

Doctors
{doctors}
"""


async def run_bot(webrtc_connection: SmallWebRTCConnection) -> None:
    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )

    stt = ElevenLabsRealtimeSTTService(
        api_key=config.ELEVENLABS_API_KEY,
        settings=ElevenLabsRealtimeSTTService.Settings(language=Language.EN),
    )

    llm = GoogleLLMService(
        api_key=config.GOOGLE_API_KEY,
        settings=GoogleLLMService.Settings(
            model=config.GOOGLE_MODEL,
            system_instruction=system_prompt(),
            temperature=0.4,
        ),
    )

    tts = ElevenLabsTTSService(
        api_key=config.ELEVENLABS_API_KEY,
        settings=ElevenLabsTTSService.Settings(
            voice=config.ELEVENLABS_VOICE_ID,
            model=config.ELEVENLABS_TTS_MODEL,
        ),
    )

    context = LLMContext(tools=tools.TOOLS)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        # Silero VAD decides when the caller starts and stops talking. That drives
        # interruptions (barge-in) and tells the realtime STT when to commit text.
        # Less sensitive than the defaults (0.7 / 0.2s / 0.6) so background noise or
        # echo doesn't count as the caller speaking and cut Maya off mid-sentence.
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(confidence=0.8, start_secs=0.35, min_volume=0.7)
            )
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
    )

    # -------------------------------------------------------------- tools
    # Each tool runs in a thread (SQLite is blocking), then we
    #  1. hand the result back to the LLM,
    #  2. tell the browser on this call (RTVI server message -> phone UI),
    #  3. tell every open dashboard (SSE -> tables refresh and highlight).

    async def notify(kind: str, **data) -> None:
        await worker.rtvi.send_server_message({"type": kind, **data})
        events.publish(kind, **data)

    def make_handler(name: str):
        fn = tools.HANDLERS[name]

        async def handler(params: FunctionCallParams) -> None:
            args = dict(params.arguments)
            logger.info(f"tool {name}({args})")
            await worker.rtvi.send_server_message({"type": "tool_started", "tool": name})
            try:
                result = await asyncio.to_thread(fn, **args)
            except TypeError as e:  # LLM sent an unexpected argument
                result = {"ok": False, "error": "bad_arguments", "message": str(e)}
            logger.info(f"tool {name} -> {result}")
            await params.result_callback(result)

            if name == "check_doctor_availability" and result.get("ok"):
                # The day being discussed: the one the caller asked for, or else the
                # earliest day with free slots. The dashboard jumps to it.
                day = tools.parse_date(args.get("date"))
                if day:
                    focus = day.isoformat()
                else:
                    days = [
                        r["next_available"][0]["iso_date"]
                        for r in result["results"]
                        if r.get("next_available")
                    ]
                    focus = min(days) if days else None
                await notify(
                    "availability_checked",
                    doctor_ids=[r["doctor_id"] for r in result["results"]],
                    date=focus,
                )
            elif name == "book_appointment" and result.get("ok"):
                await notify("appointment_booked", appointment=result["appointment"])
            elif name == "cancel_appointment" and result.get("ok"):
                await notify("appointment_cancelled", appointment=result["cancelled"])

        return handler

    for name in tools.HANDLERS:
        llm.register_function(name, make_handler(name))

    # ------------------------------------------------------------- events

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        context.add_message(
            {
                "role": "developer",
                "content": "The call just connected. Greet the caller in one short sentence, "
                "say the clinic name, and ask how you can help.",
            }
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client):
        logger.info("Call connected")
        events.publish("call_started")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client):
        logger.info("Call ended")
        events.publish("call_ended")
        await runner.cancel()

    @user_aggregator.event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(_agg, _strategy, message: UserTurnStoppedMessage):
        logger.info(f"caller: {message.content}")

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(_agg, message: AssistantTurnStoppedMessage):
        logger.info(f"agent:  {message.content}")

    await runner.run()