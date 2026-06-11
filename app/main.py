"""Точка входа FastAPI-приложения «Альфа-CBDC»."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .database import Base, engine
from .seed import seed
from .routers import clients, contracts, payments, reports
from .config import (
    CBDC_CORRIDORS, OPERATION_TYPES, TARIFFS, SMART_CONTRACT_CONDITIONS,
    LEGAL_BASIS, LOYALTY_THRESHOLD_OPS_PER_MONTH,
)

BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed()
    yield


app = FastAPI(
    title="Альфа-CBDC: трансграничные расчёты в цифровом рубле",
    version="0.1.0",
    description=(
        "MVP комплексного банковского продукта для клиентов-юридических лиц "
        "Альфа-Банка по проведению трансграничных платежей в цифровом рубле через "
        "платформу Банка России с атомарной конвертацией в e-CNY / e-AED / e-BYN."
    ),
    lifespan=lifespan,
)

app.include_router(clients.router)
app.include_router(contracts.router)
app.include_router(payments.router)
app.include_router(reports.router)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "corridors": CBDC_CORRIDORS,
            "operation_types": OPERATION_TYPES,
            "tariffs": TARIFFS,
            "sc_conditions": SMART_CONTRACT_CONDITIONS,
            "legal_basis": LEGAL_BASIS,
            "loyalty_threshold": LOYALTY_THRESHOLD_OPS_PER_MONTH,
        },
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
