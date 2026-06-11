"""API: платежи и смарт-контракты (Модули 3-4)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import Client, Contract, Payment, SmartContract
from ..services import payment_service

router = APIRouter(prefix="/api", tags=["payments"])


# ---------- Расчёт котировки ----------
@router.get("/clients/{client_id}/quote", response_model=schemas.PaymentQuote)
def quote(client_id: int, corridor: str, amount_foreign: float,
          db: Session = Depends(get_db)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Клиент не найден.")
    try:
        return payment_service.quote_payment(client, corridor, amount_foreign)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------- Инициация платежа ----------
@router.post("/clients/{client_id}/payments",
             response_model=schemas.PaymentOut, status_code=201)
def initiate(client_id: int, payload: schemas.PaymentCreate,
             db: Session = Depends(get_db)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Клиент не найден.")
    if not client.wallets:
        raise HTTPException(400, "У клиента нет кошелька цифрового рубля.")
    contract = db.get(Contract, payload.contract_id)
    if not contract:
        raise HTTPException(404, "Контракт не найден.")
    try:
        payment = payment_service.initiate_payment(
            db,
            client=client,
            wallet=client.wallets[0],
            contract=contract,
            corridor_code=payload.corridor,
            amount_foreign=payload.amount_foreign,
            payment_type=payload.payment_type,
            deadline_days=payload.deadline_days or 30,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(payment)
    return payment


@router.get("/clients/{client_id}/payments", response_model=list[schemas.PaymentOut])
def list_client_payments(client_id: int, db: Session = Depends(get_db)):
    return (
        db.query(Payment)
          .filter(Payment.client_id == client_id)
          .order_by(Payment.id.desc())
          .all()
    )


@router.get("/payments/{payment_id}", response_model=schemas.PaymentOut)
def get_payment(payment_id: int, db: Session = Depends(get_db)):
    p = db.get(Payment, payment_id)
    if not p:
        raise HTTPException(404, "Платёж не найден.")
    return p


# ---------- Смарт-контракты ----------
@router.get("/payments/{payment_id}/smart-contract",
            response_model=schemas.SmartContractOut)
def get_smart_contract(payment_id: int, db: Session = Depends(get_db)):
    p = db.get(Payment, payment_id)
    if not p or not p.smart_contract:
        raise HTTPException(404, "Смарт-контракт для платежа не найден.")
    return p.smart_contract


@router.post("/smart-contracts/{sc_id}/conditions/fulfill",
             response_model=schemas.SmartContractOut)
def fulfill_condition(sc_id: int, payload: schemas.ConditionFulfillRequest,
                      db: Session = Depends(get_db)):
    sc = db.get(SmartContract, sc_id)
    if not sc:
        raise HTTPException(404, "Смарт-контракт не найден.")
    if sc.status != "active":
        raise HTTPException(400, f"Смарт-контракт уже завершён (статус: {sc.status}).")
    try:
        sc = payment_service.fulfill_condition(
            db, sc, code=payload.code,
            document_ref=payload.document_ref, source_system=payload.source_system,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(sc)
    return sc


@router.post("/smart-contracts/{sc_id}/refund",
             response_model=schemas.SmartContractOut)
def refund(sc_id: int, db: Session = Depends(get_db)):
    sc = db.get(SmartContract, sc_id)
    if not sc:
        raise HTTPException(404, "Смарт-контракт не найден.")
    sc = payment_service.refund_smart_contract(db, sc, reason="manual_refund")
    db.commit()
    db.refresh(sc)
    return sc
