"""
ChatGPT-style API backend.

Endpoints:
  POST   /api/conversations                -> create a new conversation
  GET    /api/conversations                -> list conversations
  GET    /api/conversations/{id}            -> get a conversation + its messages
  PATCH  /api/conversations/{id}            -> rename a conversation
  DELETE /api/conversations/{id}            -> delete a conversation
  POST   /api/conversations/{id}/messages   -> send a message, stream the reply (SSE)

Run:
  uvicorn main:app --reload --port 8000
"""
import json
import os

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import database as db

load_dotenv()

MODEL = os.environ.get("MODEL", "claude-sonnet-4-6")
SYSTEM_PROMPT = "You are a helpful, concise assistant."

app = FastAPI(title="ChatGPT-style API")

# Allow the frontend (served from a different port/origin during dev) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your real frontend origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY from the environment


@app.on_event("startup")
def startup() -> None:
    db.init_db()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CreateConversationRequest(BaseModel):
    title: str = "New chat"


class RenameConversationRequest(BaseModel):
    title: str


class SendMessageRequest(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------

@app.post("/api/conversations")
def create_conversation(req: CreateConversationRequest):
    return db.create_conversation(req.title)


@app.get("/api/conversations")
def list_conversations():
    return db.list_conversations()


@app.get("/api/conversations/{conv_id}")
def get_conversation(conv_id: str):
    conv = db.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv["messages"] = db.get_messages(conv_id)
    return conv


@app.patch("/api/conversations/{conv_id}")
def rename_conversation(conv_id: str, req: RenameConversationRequest):
    if not db.get_conversation(conv_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.rename_conversation(conv_id, req.title)
    return db.get_conversation(conv_id)


@app.delete("/api/conversations/{conv_id}")
def delete_conversation(conv_id: str):
    if not db.get_conversation(conv_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete_conversation(conv_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Chat — this is the "ChatGPT" part: send a message, stream tokens back
# ---------------------------------------------------------------------------

@app.post("/api/conversations/{conv_id}/messages")
async def send_message(conv_id: str, req: SendMessageRequest):
    conv = db.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Save the user's message and build the history to send to the model
    db.add_message(conv_id, "user", req.content)
    history = db.get_messages(conv_id)
    model_messages = [{"role": m["role"], "content": m["content"]} for m in history]

    # Auto-title new conversations from the first message
    if conv["title"] == "New chat":
        db.rename_conversation(conv_id, req.content[:60])

    async def event_stream():
        full_reply = []
        try:
            async with client.messages.stream(
                model=MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=model_messages,
            ) as stream:
                async for text in stream.text_stream:
                    full_reply.append(text)
                    yield f"data: {json.dumps({'delta': text})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        # Persist the full assistant reply once streaming is done
        saved = db.add_message(conv_id, "assistant", "".join(full_reply))
        yield f"data: {json.dumps({'done': True, 'message_id': saved['id']})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/health")
def health():
    return {"status": "ok"}
