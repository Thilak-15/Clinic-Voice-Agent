# Pipeline description

The browser connects to my FastAPI server over WebRTC, using Pipecat's SmallWebRTC transport. Each call gets its own Pipecat pipeline: transport input → ElevenLabs realtime STT → user context aggregator → Gemini → ElevenLabs TTS → transport output → assistant context aggregator. Silero VAD sits in the user aggregator. It decides when the caller has finished speaking, which commits the transcript and lets the caller interrupt the agent.

Gemini has three tools registered through Pipecat function calling: `check_doctor_availability`, `book_appointment` and `cancel_appointment`. They read from and write to a SQLite database of mock doctors and 30-minute slots. The caller is identified only by the phone number they say. The prompt tells the agent to read the number back and wait for a yes. The booking and cancelling tools also refuse to run unless `phone_confirmed` is true. Booking claims the slot with a single conditional UPDATE, so a slot can't be double-booked.

After a tool succeeds, the bot sends an RTVI message to the browser on the call, which shows the booking card in the phone UI. It also sends a Server-Sent Event, so every open dashboard refreshes and highlights the change. The React dashboard uses the Pipecat JS client for the call, the live transcript and the audio levels for the waveform.
