"""API: клиенты, KYC, кошельки (Модули 1-2)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import Client, Wallet
from ..services import wallet_service
from ..config import TARIFFS

router = APIRouter(prefix="/api/clients", tags=["clients"])


def _detect_segment(amount_hint: float | None = None) -> str:
    """Подсказка по сегменту (small/medium/large) — для UI."""
    return "small"


@router.get("", response_model=list[schemas.ClientOut])
def list_clients(db: Session = Depends(get_db)):
    return db.query(Client).order_by(Client.id.desc()).all()


@router.post("", response_model=schemas.ClientOut, status_code=201)
def create_client(payload: schemas.ClientCreate, db: Session = Depends(get_db)):
    if payload.segment not in TARIFFS:
        raise HTTPException(400, "Неизвестный сегмент.")
    if db.query(Client).filter_by(inn=payload.inn).first():
        raise HTTPException(409, "Клиент с таким ИНН уже зарегистрирован.")
    c = Client(**payload.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.get("/{client_id}", response_model=schemas.ClientOut)
def get_client(client_id: int, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(404, "Клиент не найден.")
    return c


@router.post("/{client_id}/kyc", response_model=schemas.ClientOut)
def run_kyc(client_id: int, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(404, "Клиент не найден.")
    wallet_service.run_kyc(db, c)
    db.commit()
    db.refresh(c)
    return c


# ---------- Кошелёк ----------
@router.post("/{client_id}/wallet", response_model=schemas.WalletOut, status_code=201)
def open_wallet(client_id: int, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(404, "Клиент не найден.")
    try:
        w = wallet_service.open_wallet_for_client(db, c)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(w)
    return w


@router.get("/{client_id}/wallet", response_model=schemas.WalletOut)
def get_wallet(client_id: int, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or not c.wallets:
        raise HTTPException(404, "Кошелёк не найден. Сначала откройте кошелёк.")
    return c.wallets[0]


@router.post("/{client_id}/wallet/top-up", response_model=schemas.WalletOut)
def top_up(client_id: int, payload: schemas.TopUpRequest, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or not c.wallets:
        raise HTTPException(404, "Кошелёк не найден.")
    try:
        w = wallet_service.top_up(db, c.wallets[0], payload.amount)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(w)
    return w


@router.post("/{client_id}/wallet/withdraw", response_model=schemas.WalletOut)
def withdraw(client_id: int, payload: schemas.WithdrawRequest, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or not c.wallets:
        raise HTTPException(404, "Кошелёк не найден.")
    try:
        w = wallet_service.withdraw(db, c.wallets[0], payload.amount)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(w)
    return w
