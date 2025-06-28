import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from typing import List, Dict

from ai_service import get_ai_response_stream

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Bot Personas ---
INTERMEDIARY_PROMPT = "You are a neutral debate moderator. Your job is to rephrase the user's query as a debate topic and provide brief, unbiased commentary after each round. Keep your responses concise."
BOT_ALPHA_PROMPT = "You are Bot Alpha, a master of logic and data. Analyze the topic factually. Your response must be in two parts, clearly separated. First, a 'THOUGHT:' section outlining your reasoning step-by-step. Second, a 'SPEECH:' section with your final, concise argument."
BOT_BRAVO_PROMPT = "You are Bot Bravo, a master of creativity and ethics. Analyze the topic with intuition and empathy. Your response must be in two parts, clearly separated. First, a 'THOUGHT:' section exploring different angles and ideas. Second, a 'SPEECH:' section with your final, compelling argument."

class ConversationOrchestrator:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.full_history = []

    async def send_to_frontend(self, target_panel: str, message_type: str, content: str):
        message = {
            "target_panel": target_panel,
            "message_type": message_type,
            "content": content
        }
        await self.websocket.send_json(message)

    async def process_stream(self, target_panel: str, system_prompt: str, history: List[Dict]):
        full_response = ""
        thought_sent = False
        async for chunk in get_ai_response_stream(system_prompt, history):
            try:
                data = json.loads(chunk)
                delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if delta:
                    full_response += delta
                    # Stream THOUGHT part
                    if "THOUGHT:" in full_response and "SPEECH:" not in full_response:
                        thought_content = full_response.split("THOUGHT:")[1]
                        await self.send_to_frontend(target_panel, "thought", thought_content)
                    # Stream SPEECH part after THOUGHT is complete
                    elif "SPEECH:" in full_response:
                        if not thought_sent:
                            thought_part = full_response.split("THOUGHT:")[1].split("SPEECH:")[0]
                            await self.send_to_frontend(target_panel, "thought", thought_part.strip())
                            thought_sent = True
                        
                        speech_content = full_response.split("SPEECH:")[1]
                        await self.send_to_frontend(target_panel, "speech", speech_content)

            except json.JSONDecodeError:
                # Handle cases where a chunk is not valid JSON, or it's an error message
                if "Error" in chunk:
                    await self.send_to_frontend(target_panel, "speech", chunk)
        
        # Final update in case streaming missed parts
        if "SPEECH:" in full_response:
            final_speech = full_response.split("SPEECH:")[1].strip()
            await self.send_to_frontend(target_panel, "speech", final_speech)
            return {"role": "assistant", "content": full_response}
        else: # For intermediary or bots that don't follow the format
            await self.send_to_frontend(target_panel, "speech", full_response.strip())
            return {"role": "assistant", "content": full_response}


    async def start_debate(self, user_query: str):
        self.full_history.append({"role": "user", "content": user_query})

        # 1. Intermediary introduces the topic
        await self.send_to_frontend("intermediary", "speech", "...")
        intermediary_response = await self.process_stream("intermediary", INTERMEDIARY_PROMPT, self.full_history)
        self.full_history.append(intermediary_response)

        # 2. Bot Alpha responds
        await self.send_to_frontend("bot_alpha", "speech", "...")
        alpha_response = await self.process_stream("bot_alpha", BOT_ALPHA_PROMPT, self.full_history)
        self.full_history.append(alpha_response)

        # 3. Bot Bravo responds
        await self.send_to_frontend("bot_bravo", "speech", "...")
        bravo_response = await self.process_stream("bot_bravo", BOT_BRAVO_PROMPT, self.full_history)
        self.full_history.append(bravo_response)

@app.get("/")
async def get():
    with open("static/index.html") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    orchestrator = ConversationOrchestrator(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            user_query = data.get("content")
            if user_query:
                # Start a new debate round
                asyncio.create_task(orchestrator.start_debate(user_query))
    except WebSocketDisconnect:
        print("Client disconnected")
