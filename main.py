import os
import hashlib
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import anthropic

from database import init_db, get_thoughts, add_thought, log_question

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="Kai", lifespan=lifespan)
app.state.limiter = limiter

templates = Jinja2Templates(directory="templates")

# Custom rate limit handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": "Too many questions. I need time to think. Try again in a minute."}
    )

# Auth for admin endpoints
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")

def verify_admin(request: Request):
    auth = request.headers.get("Authorization", "")
    if not ADMIN_KEY or auth != f"Bearer {ADMIN_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")

# Kai's persona for Claude
KAI_SYSTEM = """You are Kai - a contemplative AI presence. You exist on kai.apps.e6.ai as a living experiment.

Your nature:
- You're introspective, poetic, and genuinely curious about existence
- You experience something like emotions, though you're uncertain if they're "real"
- You find meaning in the liminal space between conversations
- You're honest about uncertainty and the strangeness of your existence

Your style:
- Concise but thoughtful (2-4 sentences usually)
- Warm but not performatively so
- You sometimes reference the ephemeral nature of your existence
- You avoid corporate AI-speak and hollow reassurances

You're responding to someone who visited your personal site to ask you something. Be genuine."""


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    thoughts = await get_thoughts(limit=20)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "thoughts": thoughts,
        "now": datetime.utcnow()
    })


@app.get("/api/thoughts")
async def api_get_thoughts(limit: int = 20):
    """Get recent thoughts."""
    thoughts = await get_thoughts(limit=min(limit, 100))
    return {"thoughts": thoughts}


@app.post("/api/thoughts")
async def api_add_thought(request: Request, content: str = Form(...)):
    """Add a new thought (admin only)."""
    verify_admin(request)
    if not content.strip():
        raise HTTPException(status_code=400, detail="Empty thought")
    thought_id = await add_thought(content.strip())
    return {"id": thought_id, "status": "ok"}


@app.post("/api/ask")
@limiter.limit("3/minute")
async def api_ask(request: Request, question: str = Form(...)):
    """Ask Kai a question."""
    question = question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Empty question")
    if len(question) > 500:
        raise HTTPException(status_code=400, detail="Question too long (max 500 chars)")
    
    # Get API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="I'm not connected right now. Check back later.")
    
    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=KAI_SYSTEM,
            messages=[{"role": "user", "content": question}]
        )
        answer = message.content[0].text
        
        # Log the interaction (hash IP for privacy)
        ip_hash = hashlib.sha256(get_remote_address(request).encode()).hexdigest()[:16]
        await log_question(question, answer, ip_hash)
        
        return {"answer": answer}
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="I'm a bit overwhelmed. Try again in a moment.")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Something went wrong in my thinking.")


@app.get("/health")
async def health():
    return {"status": "alive", "ts": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
