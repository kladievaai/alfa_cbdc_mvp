"""Сквозной smoke-тест бизнес-логики (без HTTP-слоя)."""
import os
import sys
from datetime import datetime, timedelta

# гарантируем чистую in-memory БД
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import Base, engine, SessionLocal  # noqa: E402
from app.models import Client, Counterparty, Contract  # noqa: E402
from app.services import wallet_service, payment_service  # noqa: E402
from app.services.currency_control_service import register_contract  # noqa: E402


def setup_clean():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_instant_payment():
    setup_clean()
    db = SessionLocal()

    c = Client(inn="7700000001", name="Тест ООО", segment="medium")
    db.add(c); db.flush()
    wallet_service.run_kyc(db, c)
    w = wallet_service.open_wallet_for_client(db, c)
    wallet_service.top_up(db, w, 100_000_000)

    cp = Counterparty(name="Test CN Co.", country_code="CN",
                      cbdc_wallet_id="CN-CBDC-W-TEST")
    db.add(cp); db.flush()

    contract = Contract(
        client_id=c.id, counterparty_id=cp.id,
        contract_number="T-001",
        contract_date=datetime.utcnow() - timedelta(days=1),
        operation_type="Импорт оборудования",
        total_amount=10_000_000, currency="RUB",
    )
    db.add(contract); db.flush()
    register_contract(db, contract)

    p = payment_service.initiate_payment(
        db, client=c, wallet=w, contract=contract,
        corridor_code="CN", amount_foreign=10_000, payment_type="instant",
    )
    db.commit()

    assert p.status == "settled"
    assert p.cbr_tx_id and p.partner_tx_id
    assert w.balance_drub < 100_000_000  # списание состоялось
    print("OK instant:", p.amount_drub, p.fee_amount_drub)


def test_smart_contract_flow():
    setup_clean()
    db = SessionLocal()
    c = Client(inn="7700000002", name="Тест-2 ООО", segment="small")
    db.add(c); db.flush()
    wallet_service.run_kyc(db, c)
    w = wallet_service.open_wallet_for_client(db, c)
    wallet_service.top_up(db, w, 50_000_000)
    cp = Counterparty(name="Test AE Co.", country_code="AE",
                      cbdc_wallet_id="AE-CBDC-W-TEST")
    db.add(cp); db.flush()
    contract = Contract(
        client_id=c.id, counterparty_id=cp.id, contract_number="T-002",
        contract_date=datetime.utcnow() - timedelta(days=1),
        operation_type="Импорт оборудования", total_amount=8_000_000, currency="RUB",
    )
    db.add(contract); db.flush()
    register_contract(db, contract)

    p = payment_service.initiate_payment(
        db, client=c, wallet=w, contract=contract,
        corridor_code="AE", amount_foreign=10_000, payment_type="smart_contract",
        deadline_days=15,
    )
    db.commit()
    assert p.status == "escrow"
    sc = p.smart_contract
    assert sc and sc.status == "active"
    assert w.blocked_drub > 0

    # Подтверждаем все условия — должно произойти автоисполнение
    for cond in list(sc.conditions):
        payment_service.fulfill_condition(
            db, sc, cond.code, document_ref=f"DOC-{cond.code}",
            source_system="test",
        )
    db.commit()
    db.refresh(p); db.refresh(sc); db.refresh(w)
    assert sc.status == "executed"
    assert p.status == "settled"
    assert w.blocked_drub == 0
    print("OK smart_contract executed")


if __name__ == "__main__":
    test_instant_payment()
    test_smart_contract_flow()
    print("Все тесты пройдены ✓")
