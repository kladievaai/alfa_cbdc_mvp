"""Модуль 3: трансграничный платёж через интероперабельный коридор.

Атомарная транзакция: цифровые рубли списываются с кошелька клиента на платформе
Банка России → одновременно через интероперабельный шлюз эквивалентная сумма в
целевой ЦВЦБ зачисляется на кошелёк иностранного поставщика на платформе ЦБ-партнёра.
"""
import secrets
from datetime import datetime
from typing import Tuple

from sqlalchemy.orm import Session

from ..config import CBDC_CORRIDORS, TARIFFS, SMART_CONTRACT_CONDITIONS
from ..models import (
    Client, Wallet, Contract, Payment, SmartContract, SmartContractCondition
)
from .audit import log
from .currency_control_service import register_payment_in_vc


# ---------- расчёт котировки ----------
def get_corridor(corridor_code: str) -> dict:
    if corridor_code not in CBDC_CORRIDORS:
        raise ValueError(f"Неподдерживаемый коридор: {corridor_code}")
    return CBDC_CORRIDORS[corridor_code]


def get_tariff(client: Client) -> dict:
    return TARIFFS.get(client.segment, TARIFFS["small"])


def quote_payment(client: Client, corridor_code: str, amount_foreign: float) -> dict:
    """Расчёт стоимости платежа по согласованным котировкам ЦБ-партнёров."""
    corr = get_corridor(corridor_code)
    rate = corr["rate_to_drub"]
    amount_drub = round(amount_foreign * rate, 2)
    tariff = get_tariff(client)
    fee_pct = tariff["fee_pct"]
    fee_amount = round(amount_drub * fee_pct, 2)
    return {
        "corridor": corridor_code,
        "foreign_currency": corr["currency_code"],
        "amount_foreign": amount_foreign,
        "rate": rate,
        "amount_drub": amount_drub,
        "fee_pct": fee_pct,
        "fee_amount_drub": fee_amount,
        "total_drub": round(amount_drub + fee_amount, 2),
    }


# ---------- compliance ----------
def compliance_check(db: Session, client: Client, contract: Contract,
                     amount_drub: float) -> Tuple[bool, str]:
    """Базовая проверка комплаенса перед исполнением платежа.

    В реальной системе сюда подключаются: ПОД/ФТ-сценарии (115-ФЗ), санкционный
    скрининг, проверка лимитов кошелька, валидация контракта.
    """
    if not client.kyc_passed:
        return False, "KYC/KYB клиента не пройден (115-ФЗ)."
    if contract.client_id != client.id:
        return False, "Контракт принадлежит другому клиенту."
    if contract.status != "active":
        return False, "Контракт не активен."
    if amount_drub <= 0:
        return False, "Некорректная сумма платежа."
    return True, "ok"


# ---------- атомарная транзакция ----------
def _gen_tx_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(6).upper()}"


def initiate_payment(
    db: Session,
    *,
    client: Client,
    wallet: Wallet,
    contract: Contract,
    corridor_code: str,
    amount_foreign: float,
    payment_type: str = "instant",
    deadline_days: int = 30,
) -> Payment:
    """Инициировать трансграничный платёж.

    payment_type:
      * 'instant'         — атомарный платёж через интероперабельный коридор (Модуль 3)
      * 'smart_contract'  — сумма блокируется в эскроу (Модуль 4)
    """
    quote = quote_payment(client, corridor_code, amount_foreign)
    total_drub = quote["total_drub"]

    ok, reason = compliance_check(db, client, contract, quote["amount_drub"])
    if not ok:
        raise ValueError(f"Комплаенс отклонил операцию: {reason}")

    if wallet.balance_drub < total_drub:
        raise ValueError(
            f"Недостаточно средств: на кошельке {wallet.balance_drub:.2f} drub, "
            f"требуется {total_drub:.2f} drub (сумма + комиссия)."
        )

    payment = Payment(
        client_id=client.id,
        contract_id=contract.id,
        counterparty_id=contract.counterparty_id,
        payment_type=payment_type,
        corridor=corridor_code,
        amount_foreign=amount_foreign,
        foreign_currency=quote["foreign_currency"],
        rate=quote["rate"],
        amount_drub=quote["amount_drub"],
        fee_pct=quote["fee_pct"],
        fee_amount_drub=quote["fee_amount_drub"],
        status="initiated",
    )
    db.add(payment)
    db.flush()

    log(db, actor=f"client:{client.id}", action="payment.initiate",
        entity="payment", entity_id=payment.id,
        details={"corridor": corridor_code, "amount_foreign": amount_foreign,
                 "amount_drub": quote["amount_drub"], "type": payment_type})

    # compliance отметка
    payment.status = "compliance_passed"

    if payment_type == "smart_contract":
        _setup_smart_contract(db, payment, wallet, total_drub, deadline_days)
    else:
        _execute_instant(db, payment, wallet, total_drub)

    # Валютный контроль (Модуль 5) — формируется в любом случае при инициации
    register_payment_in_vc(db, payment=payment, contract=contract)

    return payment


def _execute_instant(db: Session, payment: Payment, wallet: Wallet, total_drub: float):
    """Атомарная транзакция: списание drub + зачисление ЦВЦБ-партнёра."""
    payment.status = "executing"

    # Списание с кошелька клиента на платформе ЦБ РФ
    wallet.balance_drub -= total_drub
    cbr_tx_id = _gen_tx_id("CBR-TX")
    payment.cbr_tx_id = cbr_tx_id

    # Зачисление на кошелёк поставщика на платформе ЦБ-партнёра
    partner_prefix = {
        "CN": "PBOC-TX", "AE": "CBUAE-TX", "BY": "NBRB-TX",
    }.get(payment.corridor, "PARTNER-TX")
    payment.partner_tx_id = _gen_tx_id(partner_prefix)

    payment.status = "settled"
    payment.settled_at = datetime.utcnow()

    log(db, actor="cbr_gateway", action="payment.atomic_settle",
        entity="payment", entity_id=payment.id,
        details={"cbr_tx": cbr_tx_id, "partner_tx": payment.partner_tx_id,
                 "amount_drub": total_drub, "amount_foreign": payment.amount_foreign,
                 "foreign_currency": payment.foreign_currency})


def _setup_smart_contract(db: Session, payment: Payment, wallet: Wallet,
                          total_drub: float, deadline_days: int):
    """Сумма блокируется на эскроу-кошельке (Модуль 4)."""
    from datetime import timedelta
    wallet.balance_drub -= total_drub
    wallet.blocked_drub += total_drub

    sc = SmartContract(
        payment_id=payment.id,
        escrow_balance_drub=total_drub,
        deadline=datetime.utcnow() + timedelta(days=deadline_days),
        status="active",
    )
    db.add(sc)
    db.flush()
    for cond in SMART_CONTRACT_CONDITIONS:
        db.add(SmartContractCondition(
            smart_contract_id=sc.id, code=cond["code"], label=cond["label"]
        ))
    payment.status = "escrow"
    log(db, actor="cbr_gateway", action="smart_contract.create",
        entity="smart_contract", entity_id=sc.id,
        details={"escrow_drub": total_drub, "deadline_days": deadline_days})


# ---------- исполнение / возврат смарт-контракта ----------
def fulfill_condition(db: Session, sc: SmartContract, code: str,
                      document_ref: str | None, source_system: str | None) -> SmartContract:
    """Отметить выполнение условия (например, получение электронной транспортной накладной)."""
    condition = next((c for c in sc.conditions if c.code == code), None)
    if condition is None:
        raise ValueError(f"Условие {code} не найдено в смарт-контракте.")
    if condition.is_fulfilled:
        return sc
    condition.is_fulfilled = True
    condition.fulfilled_at = datetime.utcnow()
    condition.document_ref = document_ref
    condition.source_system = source_system
    log(db, actor=source_system or "client",
        action="smart_contract.condition_fulfilled",
        entity="smart_contract_condition", entity_id=condition.id,
        details={"code": code, "doc_ref": document_ref})

    # Если все условия выполнены — автоматическое исполнение
    if all(c.is_fulfilled for c in sc.conditions):
        execute_smart_contract(db, sc)
    return sc


def execute_smart_contract(db: Session, sc: SmartContract) -> SmartContract:
    """Автоматическое перечисление средств поставщику при выполнении всех условий."""
    if sc.status != "active":
        return sc
    payment = sc.payment
    wallet = payment.contract.client.wallets[0]

    wallet.blocked_drub -= sc.escrow_balance_drub
    sc.escrow_balance_drub = 0.0

    partner_prefix = {
        "CN": "PBOC-TX", "AE": "CBUAE-TX", "BY": "NBRB-TX",
    }.get(payment.corridor, "PARTNER-TX")
    payment.cbr_tx_id = _gen_tx_id("CBR-TX")
    payment.partner_tx_id = _gen_tx_id(partner_prefix)
    payment.status = "settled"
    payment.settled_at = datetime.utcnow()
    sc.status = "executed"
    sc.closed_at = datetime.utcnow()

    log(db, actor="smart_contract_engine", action="smart_contract.execute",
        entity="smart_contract", entity_id=sc.id,
        details={"payment_id": payment.id})
    return sc


def refund_smart_contract(db: Session, sc: SmartContract, reason: str = "deadline") -> SmartContract:
    """Возврат средств клиенту, если условия не исполнены в установленный срок."""
    if sc.status != "active":
        return sc
    payment = sc.payment
    wallet = payment.contract.client.wallets[0]

    wallet.blocked_drub -= sc.escrow_balance_drub
    wallet.balance_drub += sc.escrow_balance_drub
    sc.escrow_balance_drub = 0.0
    sc.status = "refunded"
    sc.closed_at = datetime.utcnow()
    payment.status = "refunded"
    payment.failure_reason = reason

    log(db, actor="smart_contract_engine", action="smart_contract.refund",
        entity="smart_contract", entity_id=sc.id,
        details={"reason": reason, "payment_id": payment.id})
    return sc
