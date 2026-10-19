from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / '.env')

# pyright: reportMissingImports=false
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import initialize_database
from app.routers.auth import router as auth_router
from app.routers.inventory import router as inventory_router
from app.routers.kitchen import router as kitchen_router
from app.routers.menu import router as menu_router
from app.routers.orders import router as orders_router
from app.routers.ai import router as ai_router
from app.routers.reservations import router as reservations_router


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

app.include_router(auth_router)
app.include_router(menu_router)
app.include_router(orders_router)
app.include_router(ai_router)
app.include_router(reservations_router)
app.include_router(inventory_router)
app.include_router(kitchen_router)


@app.get("/")
def read_root():
    return {"message": "Smart Restaurant API is running"}


@app.get("/health")
def health_check():
    return {"status": "ok"}
