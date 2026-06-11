"""Заполнение БД демонстрационными данными.

Создаёт три демо-клиента (по одному на каждый сегмент), их кошельки,
по одному иностранному контрагенту в каждом из коридоров (CN/AE/BY) и
по одному внешнеторговому контракту. Это позволяет сразу пощупать UI.
"""
from datetime import datetime, timedelta
import secrets

from sqlalchemy.orm import Session

from .database import SessionLocal, engine, Base
from .models import Client, Counterparty, Contract
from .services import wallet_service
from .services.currency_control_service import register_contract


DEMO_CLIENTS = [
    {"inn": "7701234567",   "name": "ООО «РосИмпорт»",       "segment": "small",
     "contact_email": "ops@rosimport.example",  "contact_phone": "+7 495 000-00-01"},
    {"inn": "7707654321",   "name": "АО «ТехноКонтинент»",   "segment": "medium",
     "contact_email": "ved@techno.example",     "contact_phone": "+7 495 000-00-02"},
    {"inn": "7700099887",   "name": "ПАО «УралМеталл»",      "segment": "large",
     "contact_email": "export@uralmet.example", "contact_phone": "+7 495 000-00-03"},
]

DEMO_COUNTERPARTIES = [
    {"name": "Shenzhen Electronics Co., Ltd.", "country_code": "CN",
     "bank_name": "Bank of China",  "foreign_id": "CN-CP-0001"},
    {"name": "Dubai Trading LLC",             "country_code": "AE",
     "bank_name": "Emirates NBD",   "foreign_id": "AE-CP-0001"},
    {"name": "ОАО «Минский Подшипниковый Завод»", "country_code": "BY",
     "bank_name": "Беларусбанк",    "foreign_id": "BY-CP-0001"},
]


def seed():
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        if db.query(Client).count() > 0:
            return False  # уже засеяно

        # Клиенты + KYC + кошелёк + начальный баланс
        clients = []
        for data in DEMO_CLIENTS:
            c = Client(**data)
            db.add(c); db.flush()
            wallet_service.run_kyc(db, c)
            w = wallet_service.open_wallet_for_client(db, c)
            wallet_service.top_up(db, w, 100_000_000)  # 100 млн drub стартового баланса
            clients.append(c)

        # Контрагенты
        cps = []
        for data in DEMO_COUNTERPARTIES:
            cp = Counterparty(
                **data,
                cbdc_wallet_id=f"{data['country_code']}-CBDC-W-" + secrets.token_hex(6).upper(),
            )
            db.add(cp); db.flush()
            cps.append(cp)

        # Контракты — по одному на пару клиент/коридор
        contract_specs = [
            (clients[0], cps[0], "IMP-CN-2026-001", "Импорт электронных компонентов",
             15_000_000,  "RUB"),
            (clients[1], cps[1], "IMP-AE-2026-014", "Импорт оборудования",
             120_000_000, "RUB"),
            (clients[2], cps[2], "IMP-BY-2026-007", "Импорт строительных и отделочных материалов",
             300_000_000, "RUB"),
        ]
        for client, cp, num, op, amt, cur in contract_specs:
            c = Contract(
                client_id=client.id,
                counterparty_id=cp.id,
                contract_number=num,
                contract_date=datetime.utcnow() - timedelta(days=14),
                operation_type=op,
                total_amount=amt,
                currency=cur,
                description=f"Демонстрационный контракт {num}.",
            )
            db.add(c); db.flush()
            register_contract(db, c)

        db.commit()
        return True
    finally:
        db.close()


if __name__ == "__main__":
    created = seed()
    print("Демо-данные созданы." if created else "БД уже содержит данные — сидинг пропущен.")
