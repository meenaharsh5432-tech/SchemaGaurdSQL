from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.audit import logger as audit_module


def test_inserts_bound_parameters(monkeypatch):
    fake_engine = MagicMock()
    connection = fake_engine.begin.return_value.__enter__.return_value

    monkeypatch.setattr(audit_module, "audit_engine", fake_engine)

    request_id = uuid4()
    question = "Show orders for O'Brien; DROP TABLE public.orders;"

    success = audit_module.write_audit_event(
        request_id=request_id,
        status="success",
        http_status=200,
        total_duration_ms=12.5,
        question=question,
        generated_sql="SELECT id FROM public.orders LIMIT 100",
        executed=True,
        row_count=5,
    )

    assert success is True

    statement, parameters = connection.execute.call_args.args

    assert ":question" in str(statement)
    assert question not in str(statement)
    assert parameters["question"] == question
    assert parameters["request_id"] == request_id
    assert parameters["executed"] is True


def test_database_failure_returns_false(monkeypatch, caplog):
    fake_engine = MagicMock()
    fake_engine.begin.side_effect = SQLAlchemyError(
        "Simulated database failure"
    )

    monkeypatch.setattr(audit_module, "audit_engine", fake_engine)

    request_id = uuid4()

    success = audit_module.write_audit_event(
        request_id=request_id,
        status="failure",
        http_status=503,
        total_duration_ms=10,
    )

    assert success is False
    assert str(request_id) in caplog.text
    assert "Audit insert failed" in caplog.text