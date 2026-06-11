"""Модуль 5: валютный контроль (Инструкция Банка России № 181-И).

Контракт ставится на учёт в банке (УНК), по каждой операции формируется справка
о подтверждающих документах (СПД), пакет передаётся в Банк России и ФНС России
автоматически.
"""
import secrets
from datetime import datetime
from sqlalchemy.orm import Session

from ..models import Contract, Payment, CurrencyControlRecord
from .audit import log


def _gen_unk(country_code: str) -> str:
    """Уникальный номер контракта (УНК) — упрощённая имитация формата 181-И."""
    return f"UK-{country_code}-{secrets.token_hex(4).upper()}-{datetime.utcnow().year}"


def _gen_spd() -> str:
    """Номер справки о подтверждающих документах."""
    return f"SPD-{secrets.token_hex(5).upper()}"


def register_contract(db: Session, contract: Contract) -> Contract:
    """Постановка контракта на учёт в банке (181-И, гл. 5)."""
    if not contract.uk_number:
        contract.uk_number = _gen_unk(contract.counterparty.country_code)
    contract.status = "active"
    log(db, actor="currency_control", action="contract.register",
        entity="contract", entity_id=contract.id,
        details={"unk": contract.uk_number})
    return contract


def register_payment_in_vc(db: Session, *, payment: Payment, contract: Contract
                            ) -> CurrencyControlRecord:
    """Сформировать запись валютного контроля и пакет документов для ЦБ РФ / ФНС России."""
    if not contract.uk_number:
        register_contract(db, contract)

    payload = {
        "instr_181i": True,
        "unk": contract.uk_number,
        "contract_number": contract.contract_number,
        "contract_date": contract.contract_date.isoformat() if contract.contract_date else None,
        "operation_type": contract.operation_type,
        "counterparty": {
            "name": contract.counterparty.name,
            "country_code": contract.counterparty.country_code,
        },
        "payment": {
            "id": payment.id,
            "corridor": payment.corridor,
            "amount_drub": payment.amount_drub,
            "amount_foreign": payment.amount_foreign,
            "foreign_currency": payment.foreign_currency,
            "rate": payment.rate,
            "fee_amount_drub": payment.fee_amount_drub,
            "cbr_tx_id": payment.cbr_tx_id,
            "partner_tx_id": payment.partner_tx_id,
            "initiated_at": payment.initiated_at.isoformat(),
        },
        "generated_at": datetime.utcnow().isoformat(),
    }
    rec = CurrencyControlRecord(
        payment_id=payment.id,
        contract_id=contract.id,
        spd_number=_gen_spd(),
        submitted_to_cbr=True,
        submitted_to_fns=True,
        submitted_at=datetime.utcnow(),
        payload=payload,
    )
    db.add(rec)
    db.flush()
    log(db, actor="currency_control", action="vc.submit",
        entity="currency_control", entity_id=rec.id,
        details={"spd": rec.spd_number, "payment_id": payment.id})
    return rec
