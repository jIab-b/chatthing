import os
import httpx
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4o-mini" # Using the specified model

async def get_ai_response_stream(system_prompt: str, messages: list):
    """
    Gets a streaming response from the OpenAI API.
    Yields chunks of the response as they are received.
    """
    if not OPENAI_API_KEY or OPENAI_API_KEY == "your-openai-api-key-here":
        yield "Error: OpenAI API key not configured."
        return

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    all_messages = [{"role": "system", "content": system_prompt}] + messages
    
    data = {
        "model": MODEL,
        "messages": all_messages,
        "stream": True
    }

    async with httpx.AsyncClient(timeout=None) as client:
        try:
            async with client.stream("post", "https://api.openai.com/v1/chat/completions", headers=headers, json=data) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    yield f"Error from OpenAI: {response.status_code} - {error_text.decode()}"
                    return
                
                async for chunk in response.aiter_bytes():
                    # Process server-sent events
                    for line in chunk.decode('utf-8').splitlines():
                        if line.startswith('data: '):
                            line_data = line[6:]
                            if line_data.strip() == '[DONE]':
                                return
                            yield line_data
        except httpx.RequestError as e:
            yield f"Error connecting to OpenAI: {e}"