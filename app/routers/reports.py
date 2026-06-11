"""API: отчётность валютного контроля (Модуль 5) и дашборд."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import schemas
from ..database import get_db
from ..models import (
    Client, Wallet, Contract, Payment, SmartContract,
    CurrencyControlRecord, AuditLogEntry,
)
from ..config import CBDC_CORRIDORS, LOYALTY_THRESHOLD_OPS_PER_MONTH

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/payments/{payment_id}/currency-control",
            response_model=schemas.CurrencyControlOut)
def get_vc_record(payment_id: int, db: Session = Depends(get_db)):
    rec = (
        db.query(CurrencyControlRecord)
          .filter(CurrencyControlRecord.payment_id == payment_id)
          .first()
    )
    if not rec:
        raise HTTPException(404, "Запись валютного контроля не найдена.")
    return rec


@router.get("/dashboard", response_model=schemas.DashboardStats)
def dashboard(db: Session = Depends(get_db)):
    settled = db.query(func.count(Payment.id)).filter(Payment.status == "settled").scalar() or 0
    pending = (
        db.query(func.count(Payment.id))
          .filter(Payment.status.in_(["initiated", "compliance_passed", "executing", "escrow"]))
          .scalar() or 0
    )
    volume = (
        db.query(func.coalesce(func.sum(Payment.amount_drub), 0.0))
          .filter(Payment.status == "settled")
          .scalar() or 0.0
    )
    fees = (
        db.query(func.coalesce(func.sum(Payment.fee_amount_drub), 0.0))
          .filter(Payment.status == "settled")
          .scalar() or 0.0
    )

    # Программа лояльности (Модуль 6): клиенты ≥5 платежей за последние 30 дней
    cutoff = datetime.utcnow() - timedelta(days=30)
    rows = (
        db.query(Payment.client_id, func.count(Payment.id).label("cnt"))
          .filter(Payment.initiated_at >= cutoff)
          .group_by(Payment.client_id)
          .all()
    )
    loyalty = sum(1 for _, cnt in rows if cnt >= LOYALTY_THRESHOLD_OPS_PER_MONTH)

    return schemas.DashboardStats(
        clients=db.query(func.count(Client.id)).scalar() or 0,
        wallets=db.query(func.count(Wallet.id)).scalar() or 0,
        contracts=db.query(func.count(Contract.id)).scalar() or 0,
        payments_settled=settled,
        payments_pending=pending,
        smart_contracts_active=db.query(func.count(SmartContract.id))
                                  .filter(SmartContract.status == "active").scalar() or 0,
        total_volume_drub=float(volume),
        total_fees_drub=float(fees),
        loyalty_clients=loyalty,
    )


@router.get("/audit")
def audit(limit: int = 50, db: Session = Depends(get_db)):
    rows = (
        db.query(AuditLogEntry)
          .order_by(AuditLogEntry.ts.desc())
          .limit(limit)
          .all()
    )
    return [
        {"id": r.id, "ts": r.ts.isoformat(), "actor": r.actor,
         "action": r.action, "entity": r.entity, "entity_id": r.entity_id,
         "details": r.details}
        for r in rows
    ]


@router.get("/corridors")
def corridors():
    """Доступные коридоры ЦВЦБ."""
    return [
        {
            "code": code,
            "name": data["name"],
            "currency_code": data["currency_code"],
            "currency_name": data["currency_name"],
            "central_bank": data["central_bank"],
            "rate_to_drub": data["rate_to_drub"],
            "share_pct": data["share_pct"],
            "flag": data["flag"],
        }
        for code, data in CBDC_CORRIDORS.items()
    ]
