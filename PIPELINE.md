I built the voice agent with Pipecat in Python. When you click Try call on the dashboard, the browser opens a WebRTC connection to my FastAPI server, and Pipecat starts a pipeline for that call.

The flow is: caller audio → Silero VAD (detects when the caller starts and stops talking) → ElevenLabs speech-to-text → Gemini 3.5 Flash-Lite → ElevenLabs text-to-speech → back to the caller.

Gemini has three tools registered through Pipecat function calling: check_doctor_availability, book_appointment and cancel_appointment. They work on a small SQLite database of mock doctors and 30-minute slots. The caller is identified only by the phone number they say. The agent reads it back, and the booking and cancelling tools won't run until the caller confirms it, so this is checked in code and not just in the prompt.

Whenever a tool changes something, the server pushes an event to the dashboard, which refreshes the schedule and appointment list and highlights what changed.

I used AI tools while building this. Getting it running end to end was my part, and it took some debugging: the first Gemini model kept returning 503 errors because of high demand, so I switched to Flash-Lite, which is also faster for voice. Speech-to-text was guessing the language, so I fixed it to English. The agent was skipping the patient's name, so I tightened the prompt. And the agent's voice wasn't playing in the browser because of how the audio track was being detected, which I fixed in the frontend.