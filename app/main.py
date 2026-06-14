from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .errors import register_handlers
from .routers import auth, posts, users

app = FastAPI(
    title="Social Media API (FastAPI)",
    description="FastAPI implementation of the shared social-media API contract.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_handlers(app)

app.include_router(auth.router)
app.include_router(auth.dev_router)
app.include_router(users.router)
app.include_router(posts.router)


@app.get("/api/health", tags=["health"])
async def health():
    return {"status": "ok", "backend": "fastapi"}
