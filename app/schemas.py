"""Pydantic-схемы для API."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ---------- Клиент ----------
class ClientCreate(BaseModel):
    inn: str = Field(..., min_length=10, max_length=12)
    name: str
    ogrn: Optional[str] = None
    segment: str = "small"
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


class ClientOut(BaseModel):
    id: int
    inn: str
    name: str
    segment: str
    kyc_passed: bool
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True


# ---------- Кошелёк ----------
class WalletOut(BaseModel):
    id: int
    client_id: int
    cbr_wallet_id: str
    balance_drub: float
    blocked_drub: float
    status: str
    opened_at: datetime
    class Config:
        from_attributes = True


class TopUpRequest(BaseModel):
    amount: float = Field(..., gt=0)


class WithdrawRequest(BaseModel):
    amount: float = Field(..., gt=0)


# ---------- Контрагент / Контракт ----------
class CounterpartyCreate(BaseModel):
    name: str
    country_code: str = Field(..., min_length=2, max_length=2)
    foreign_id: Optional[str] = None
    bank_name: Optional[str] = None


class CounterpartyOut(BaseModel):
    id: int
    name: str
    country_code: str
    foreign_id: Optional[str] = None
    cbdc_wallet_id: Optional[str] = None
    bank_name: Optional[str] = None
    class Config:
        from_attributes = True


class ContractCreate(BaseModel):
    counterparty_id: int
    contract_number: str
    contract_date: datetime
    operation_type: str
    total_amount: float = Field(..., gt=0)
    currency: str
    description: Optional[str] = None


class ContractOut(BaseModel):
    id: int
    client_id: int
    counterparty_id: int
    contract_number: str
    contract_date: datetime
    operation_type: str
    total_amount: float
    currency: str
    description: Optional[str] = None
    uk_number: Optional[str] = None
    registered_at: datetime
    status: str
    class Config:
        from_attributes = True


# ---------- Платёж ----------
class PaymentCreate(BaseModel):
    contract_id: int
    corridor: str = Field(..., min_length=2, max_length=2)   # CN / AE / BY
    amount_foreign: float = Field(..., gt=0)
    payment_type: str = "instant"                            # instant / smart_contract
    deadline_days: Optional[int] = 30                        # для смарт-контракта


class PaymentQuote(BaseModel):
    corridor: str
    foreign_currency: str
    amount_foreign: float
    rate: float
    amount_drub: float
    fee_pct: float
    fee_amount_drub: float
    total_drub: float


class PaymentOut(BaseModel):
    id: int
    client_id: int
    contract_id: int
    counterparty_id: int
    payment_type: str
    corridor: str
    amount_foreign: float
    foreign_currency: str
    rate: float
    amount_drub: float
    fee_pct: float
    fee_amount_drub: float
    status: str
    cbr_tx_id: Optional[str] = None
    partner_tx_id: Optional[str] = None
    initiated_at: datetime
    settled_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    class Config:
        from_attributes = True


# ---------- Смарт-контракт ----------
class SmartContractConditionOut(BaseModel):
    id: int
    code: str
    label: str
    is_fulfilled: bool
    fulfilled_at: Optional[datetime] = None
    document_ref: Optional[str] = None
    source_system: Optional[str] = None
    class Config:
        from_attributes = True


class SmartContractOut(BaseModel):
    id: int
    payment_id: int
    escrow_balance_drub: float
    deadline: datetime
    status: str
    created_at: datetime
    closed_at: Optional[datetime] = None
    conditions: List[SmartContractConditionOut] = []
    class Config:
        from_attributes = True


class ConditionFulfillRequest(BaseModel):
    code: str
    document_ref: Optional[str] = None
    source_system: Optional[str] = None


# ---------- Валютный контроль ----------
class CurrencyControlOut(BaseModel):
    id: int
    payment_id: int
    contract_id: int
    spd_number: Optional[str] = None
    submitted_to_cbr: bool
    submitted_to_fns: bool
    submitted_at: Optional[datetime] = None
    payload: Optional[Dict[str, Any]] = None
    class Config:
        from_attributes = True


# ---------- Дашборд ----------
class DashboardStats(BaseModel):
    clients: int
    wallets: int
    contracts: int
    payments_settled: int
    payments_pending: int
    smart_contracts_active: int
    total_volume_drub: float
    total_fees_drub: float
    loyalty_clients: int
