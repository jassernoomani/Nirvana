from contextlib import asynccontextmanager

# pyright: reportMissingImports=false
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import initialize_database
from app.routers.menu import router as menu_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Smart Restaurant API",
    description="Backend API for restaurant operations and online ordering.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(menu_router)


@app.get("/")
def read_root():
    return {"message": "Smart Restaurant API is running"}


@app.get("/health")
def health_check():
    return {"status": "ok"}