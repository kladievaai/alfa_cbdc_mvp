"""API: внешнеторговые контракты и контрагенты."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import Client, Counterparty, Contract
from ..config import CBDC_CORRIDORS, OPERATION_TYPES
from ..services.currency_control_service import register_contract

router = APIRouter(prefix="/api", tags=["contracts"])


# ---------- Контрагенты ----------
@router.get("/counterparties", response_model=list[schemas.CounterpartyOut])
def list_counterparties(db: Session = Depends(get_db)):
    return db.query(Counterparty).order_by(Counterparty.id.desc()).all()


@router.post("/counterparties", response_model=schemas.CounterpartyOut, status_code=201)
def create_counterparty(payload: schemas.CounterpartyCreate, db: Session = Depends(get_db)):
    if payload.country_code not in CBDC_CORRIDORS:
        raise HTTPException(400, "Неподдерживаемая страна (доступно: CN, AE, BY).")
    import secrets
    cp = Counterparty(
        **payload.model_dump(),
        cbdc_wallet_id=f"{payload.country_code}-CBDC-W-" + secrets.token_hex(6).upper(),
    )
    db.add(cp)
    db.commit()
    db.refresh(cp)
    return cp


# ---------- Контракты ----------
@router.get("/clients/{client_id}/contracts", response_model=list[schemas.ContractOut])
def list_contracts(client_id: int, db: Session = Depends(get_db)):
    return (
        db.query(Contract)
          .filter(Contract.client_id == client_id)
          .order_by(Contract.id.desc())
          .all()
    )


@router.post("/clients/{client_id}/contracts",
             response_model=schemas.ContractOut, status_code=201)
def create_contract(client_id: int, payload: schemas.ContractCreate,
                    db: Session = Depends(get_db)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Клиент не найден.")
    cp = db.get(Counterparty, payload.counterparty_id)
    if not cp:
        raise HTTPException(404, "Контрагент не найден.")
    if payload.operation_type not in OPERATION_TYPES:
        raise HTTPException(400, f"Тип операции не входит в перечень: {OPERATION_TYPES}.")
    if db.query(Contract).filter_by(contract_number=payload.contract_number).first():
        raise HTTPException(409, "Контракт с таким номером уже зарегистрирован.")
    contract = Contract(
        client_id=client.id,
        counterparty_id=cp.id,
        contract_number=payload.contract_number,
        contract_date=payload.contract_date,
        operation_type=payload.operation_type,
        total_amount=payload.total_amount,
        currency=payload.currency,
        description=payload.description,
    )
    db.add(contract)
    db.flush()
    # Автоматическая постановка на учёт (Инструкция 181-И)
    register_contract(db, contract)
    db.commit()
    db.refresh(contract)
    return contract


@router.get("/contracts/{contract_id}", response_model=schemas.ContractOut)
def get_contract(contract_id: int, db: Session = Depends(get_db)):
    c = db.get(Contract, contract_id)
    if not c:
        raise HTTPException(404, "Контракт не найден.")
    return c
