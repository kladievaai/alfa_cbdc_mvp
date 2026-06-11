"""Модули 1-2: открытие кошелька, пополнение, вывод."""
import secrets
from datetime import datetime
from sqlalchemy.orm import Session

from ..models import Client, Wallet
from .audit import log


def _gen_cbr_wallet_id() -> str:
    """Имитация ID кошелька на платформе Банка России."""
    return "CBR-W-" + secrets.token_hex(8).upper()


def open_wallet_for_client(db: Session, client: Client) -> Wallet:
    """Открыть кошелёк цифрового рубля для прошедшего KYC клиента (Модуль 1).

    Юридическое основание: ФЗ № 340-ФЗ + нормативные акты Банка России.
    KYC/KYB по ФЗ № 115-ФЗ требуется до открытия кошелька.
    """
    if not client.kyc_passed:
        raise ValueError("KYC/KYB по ФЗ-115 не пройден — открытие кошелька невозможно.")
    if client.wallets:
        return client.wallets[0]
    w = Wallet(
        client_id=client.id,
        cbr_wallet_id=_gen_cbr_wallet_id(),
        balance_drub=0.0,
        blocked_drub=0.0,
    )
    db.add(w)
    db.flush()
    log(db, actor=f"client:{client.id}", action="wallet.open",
        entity="wallet", entity_id=w.id, details={"cbr_wallet_id": w.cbr_wallet_id})
    return w


def top_up(db: Session, wallet: Wallet, amount: float) -> Wallet:
    """Пополнение кошелька с расчётного счёта в Альфа-Банке.

    Соотношение 1:1, без комиссии за пополнение (Модуль 2).
    """
    if amount <= 0:
        raise ValueError("Сумма пополнения должна быть положительной.")
    wallet.balance_drub += amount
    log(db, actor=f"client:{wallet.client_id}", action="wallet.top_up",
        entity="wallet", entity_id=wallet.id,
        details={"amount": amount, "new_balance": wallet.balance_drub})
    return wallet


def withdraw(db: Session, wallet: Wallet, amount: float) -> Wallet:
    """Вывод цифровых рублей обратно в безналичную форму (Модуль 2)."""
    if amount <= 0:
        raise ValueError("Сумма вывода должна быть положительной.")
    if wallet.balance_drub < amount:
        raise ValueError("Недостаточно цифровых рублей на кошельке.")
    wallet.balance_drub -= amount
    log(db, actor=f"client:{wallet.client_id}", action="wallet.withdraw",
        entity="wallet", entity_id=wallet.id,
        details={"amount": amount, "new_balance": wallet.balance_drub})
    return wallet


def run_kyc(db: Session, client: Client) -> Client:
    """Имитация процедуры KYC/KYB по ФЗ-115."""
    client.kyc_passed = True
    client.kyc_passed_at = datetime.utcnow()
    log(db, actor="compliance", action="kyc.pass",
        entity="client", entity_id=client.id, details={"inn": client.inn})
    return client
