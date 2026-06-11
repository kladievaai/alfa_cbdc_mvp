"""Модели данных сервиса «Альфа-CBDC».

Соответствие функциональным модулям продукта:
  Модуль 1: Client + Wallet (кошелёк цифрового рубля юрлица)
  Модуль 2: Wallet.top_up / Wallet.withdraw (пополнение / вывод)
  Модуль 3: Payment (трансграничный платёж через интероперабельный коридор)
  Модуль 4: SmartContract + SmartContractCondition (эскроу «безопасная сделка»)
  Модуль 5: CurrencyControlRecord (валютный контроль, 181-И)
  Модуль 6: метрики в Client (программа лояльности, ≥5 операций/мес)
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text, JSON
)
from sqlalchemy.orm import relationship

from ..database import Base


class Client(Base):
    """Клиент-юридическое лицо Альфа-Банка (ВЭД-сегмент)."""
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    inn = Column(String(12), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    ogrn = Column(String(15))
    segment = Column(String(20), default="small")           # small / medium / large
    kyc_passed = Column(Boolean, default=False)             # 115-ФЗ KYC/KYB
    kyc_passed_at = Column(DateTime, nullable=True)
    contact_email = Column(String(255))
    contact_phone = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

    wallets = relationship("Wallet", back_populates="client", cascade="all,delete")
    contracts = relationship("Contract", back_populates="client", cascade="all,delete")


class Wallet(Base):
    """Кошелёк цифрового рубля юрлица на платформе Банка России."""
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    cbr_wallet_id = Column(String(64), unique=True, index=True)    # ID кошелька на платформе ЦБ РФ
    balance_drub = Column(Float, default=0.0)                       # цифровых рублей
    blocked_drub = Column(Float, default=0.0)                       # в эскроу по смарт-контрактам
    status = Column(String(20), default="active")
    opened_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="wallets")


class Counterparty(Base):
    """Иностранный контрагент-получатель платежа."""
    __tablename__ = "counterparties"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    country_code = Column(String(2))                       # CN / AE / BY
    foreign_id = Column(String(64))                        # ИД в системе ЦВЦБ контрагента
    cbdc_wallet_id = Column(String(64))                    # кошелёк на платформе ЦБ-партнёра
    bank_name = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)


class Contract(Base):
    """Внешнеторговый контракт, поставленный на учёт (Инструкция 181-И)."""
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"))
    contract_number = Column(String(64), unique=True, index=True)
    contract_date = Column(DateTime)
    operation_type = Column(String(100))                   # тип ВЭД-операции
    total_amount = Column(Float)                           # сумма контракта в валюте контракта
    currency = Column(String(10))                          # RUB / CNY / AED / BYN
    description = Column(Text)
    uk_number = Column(String(64))                         # уникальный номер контракта (УНК)
    registered_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="active")

    client = relationship("Client", back_populates="contracts")
    counterparty = relationship("Counterparty")


class Payment(Base):
    """Трансграничный платёж (Модуль 3) — атомарная транзакция drub → ЦВЦБ-партнёра."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    contract_id = Column(Integer, ForeignKey("contracts.id"))
    counterparty_id = Column(Integer, ForeignKey("counterparties.id"))

    # Параметры сделки
    payment_type = Column(String(20), default="instant")   # instant / smart_contract
    corridor = Column(String(2))                           # CN / AE / BY
    amount_foreign = Column(Float)                         # сумма в валюте контрагента (e-CNY и т.д.)
    foreign_currency = Column(String(10))                  # e-CNY / e-AED / e-BYN
    rate = Column(Float)                                   # курс drub за единицу ЦВЦБ-партнёра
    amount_drub = Column(Float)                            # сумма в цифровых рублях
    fee_pct = Column(Float)                                # тарифный процент
    fee_amount_drub = Column(Float)                        # комиссия в цифровых рублях

    # Исполнение
    status = Column(String(20), default="initiated")
    # initiated → compliance_passed → executing → settled / failed / refunded
    cbr_tx_id = Column(String(64))                         # ID транзакции на платформе ЦБ РФ
    partner_tx_id = Column(String(64))                     # ID транзакции на платформе ЦБ-партнёра
    initiated_at = Column(DateTime, default=datetime.utcnow)
    settled_at = Column(DateTime, nullable=True)
    failure_reason = Column(Text, nullable=True)

    contract = relationship("Contract")
    counterparty = relationship("Counterparty")
    smart_contract = relationship(
        "SmartContract", back_populates="payment", uselist=False, cascade="all,delete"
    )


class SmartContract(Base):
    """Смарт-контракт «безопасная сделка» (Модуль 4)."""
    __tablename__ = "smart_contracts"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), unique=True)
    escrow_balance_drub = Column(Float, default=0.0)       # сумма в эскроу
    deadline = Column(DateTime)                            # срок исполнения условий
    status = Column(String(20), default="active")
    # active → executed / refunded / expired
    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    payment = relationship("Payment", back_populates="smart_contract")
    conditions = relationship(
        "SmartContractCondition", back_populates="smart_contract",
        cascade="all,delete-orphan",
    )


class SmartContractCondition(Base):
    """Условие исполнения смарт-контракта."""
    __tablename__ = "smart_contract_conditions"

    id = Column(Integer, primary_key=True, index=True)
    smart_contract_id = Column(Integer, ForeignKey("smart_contracts.id"))
    code = Column(String(40))                              # transport_doc / customs_cleared / goods_accepted
    label = Column(String(255))
    is_fulfilled = Column(Boolean, default=False)
    fulfilled_at = Column(DateTime, nullable=True)
    document_ref = Column(String(255))                     # ссылка на цифровой документ
    source_system = Column(String(64))                     # ФТС / клиент / транспортная

    smart_contract = relationship("SmartContract", back_populates="conditions")


class CurrencyControlRecord(Base):
    """Запись валютного контроля (Модуль 5, Инструкция Банка России № 181-И)."""
    __tablename__ = "currency_control"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"))
    contract_id = Column(Integer, ForeignKey("contracts.id"))
    spd_number = Column(String(64))                        # справка о подтверждающих документах
    submitted_to_cbr = Column(Boolean, default=False)
    submitted_to_fns = Column(Boolean, default=False)
    submitted_at = Column(DateTime, nullable=True)
    payload = Column(JSON)                                 # сформированный пакет документов


class AuditLogEntry(Base):
    """Журнал аудита всех значимых операций."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    actor = Column(String(64))
    action = Column(String(64))
    entity = Column(String(64))
    entity_id = Column(Integer)
    details = Column(JSON)
