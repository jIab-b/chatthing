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
BOT_BRAVO_PROMPT = "You are Bot Bravo, a creative thinker. Your response must be in two parts, clearly separated. First, a 'THOUGHT:' section exploring different angles and ideas. Second, a 'SPEECH:' section with your final, compelling argument. On your second turn, you must refine your initial idea based on the logical bot's counter-argument."
BOT_ALPHA_PROMPT = "You are Bot Alpha, a logical analyst. Your response must be in two parts, clearly separated. First, a 'THOUGHT:' section outlining your reasoning step-by-step. Second, a 'SPEECH:' section with your final, concise argument. On your second turn, you must provide your final, definitive answer based on all previous arguments."
JUDGE_PROMPT = "You are a judge. You will be given two final arguments from two different bots in response to a user's prompt. Your task is to analyze both arguments and declare which one is 'best' and why, in a concise summary."

class ConversationOrchestrator:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.full_history: List[Dict] = []

    async def send_to_frontend(self, target_panel: str, message_type: str, content: str):
        message = {
            "target_panel": target_panel,
            "message_type": message_type,
            "content": content
        }
        await self.websocket.send_json(message)

    async def process_stream(self, target_panel: str, system_prompt: str, history: List[Dict]) -> str:
        full_response = ""
        thought_sent = False
        async for chunk in get_ai_response_stream(system_prompt, history):
            try:
                data = json.loads(chunk)
                delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if delta:
                    full_response += delta
                    if "THOUGHT:" in full_response and "SPEECH:" not in full_response:
                        thought_content = full_response.split("THOUGHT:")[1]
                        await self.send_to_frontend(target_panel, "thought", thought_content)
                    elif "SPEECH:" in full_response:
                        if not thought_sent:
                            thought_part = full_response.split("THOUGHT:")[1].split("SPEECH:")[0]
                            await self.send_to_frontend(target_panel, "thought", thought_part.strip())
                            thought_sent = True
                        speech_content = full_response.split("SPEECH:")[1]
                        await self.send_to_frontend(target_panel, "speech", speech_content)
            except (json.JSONDecodeError, IndexError):
                 if "Error" in chunk:
                    await self.send_to_frontend(target_panel, "speech", chunk)
                    return chunk

        # Final update for judge or non-compliant bots
        if "SPEECH:" not in full_response:
             await self.send_to_frontend(target_panel, "speech", full_response.strip())
        
        self.full_history.append({"role": "assistant", "content": full_response})
        return full_response.strip()


    async def start_sequence(self, user_query: str):
        self.full_history = [{"role": "user", "content": user_query}]
        await self.send_to_frontend("user", "speech", user_query)

        # Round 1
        await self.process_stream("bot_bravo", BOT_BRAVO_PROMPT, self.full_history)
        await self.process_stream("bot_alpha", BOT_ALPHA_PROMPT, self.full_history)

        # Round 2
        await self.process_stream("bot_bravo", BOT_BRAVO_PROMPT, self.full_history)
        await self.process_stream("bot_alpha", BOT_ALPHA_PROMPT, self.full_history)

        # Judge
        final_bravo = self.full_history[-2]['content']
        final_alpha = self.full_history[-1]['content']
        judge_history = [
            {"role": "user", "content": f"Here are two final arguments in response to the prompt '{user_query}'. Argument A (from Bravo): {final_bravo}. Argument B (from Alpha): {final_alpha}. Which is best and why?"}
        ]
        await self.process_stream("intermediary", JUDGE_PROMPT, judge_history)


@app.get("/")
async def get():
    with open("static/index.html") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            user_query = data.get("content")
            if user_query:
                orchestrator = ConversationOrchestrator(websocket)
                asyncio.create_task(orchestrator.start_sequence(user_query))
    except WebSocketDisconnect:
        print("Client disconnected")
