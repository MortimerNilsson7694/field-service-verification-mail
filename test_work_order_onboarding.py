import pytest

from work_order_onboarding import Infrai, InfraiError, WorkOrderOnboarding


def test_assigned_work_order_requests_verification_and_photo_follow_up() -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    def transport(method: str, path: str, payload: dict[str, object]):
        calls.append((method, path, payload))
        if path == "/auth/user/create":
            return 200, {}, {"ok": True, "data": {"user_id": "tech-42"}}
        if path == "/auth/email/send_code":
            return 200, {}, {"ok": True, "data": {}}
        return 200, {}, {"ok": True, "data": {"message_id": "mail-17"}}

    outcome = WorkOrderOnboarding(Infrai("test-key", transport=transport)).sign_up(
        email="tech@example.com",
        password="correct-horse-battery-staple",
        name="Mina",
        work_order_id="WO-204",
        photo_count=3,
        dispatch_status="assigned",
        technician_follow_up=True,
    )

    assert outcome.user_id == "tech-42"
    assert outcome.verification_requested is True
    assert outcome.follow_up_message_id == "mail-17"
    assert [path for _, path, _ in calls] == [
        "/auth/user/create",
        "/auth/email/send_code",
        "/email/send",
    ]
    assert calls[0][2]["metadata"] == {
        "work_order_id": "WO-204",
        "photo_count": 3,
        "dispatch_status": "assigned",
        "technician_follow_up": True,
    }


def test_failed_verification_request_removes_created_user() -> None:
    calls = []

    def transport(method, path, payload):
        calls.append((method, path))
        if path == "/auth/user/create":
            return 200, {}, {"ok": True, "data": {"user_id": "tech-42"}}
        if path == "/auth/email/send_code":
            return 400, {}, {"ok": False, "error": {"code": "EMAIL_REJECTED"}}
        return 200, {}, {"ok": True, "data": {}}

    with pytest.raises(InfraiError, match="EMAIL_REJECTED"):
        WorkOrderOnboarding(Infrai("test-key", transport=transport)).sign_up(
            email="tech@example.com", password="correct-horse-battery-staple", name="Mina",
            work_order_id="WO-204", photo_count=3, dispatch_status="assigned",
            technician_follow_up=True,
        )
    assert calls == [
        ("POST", "/auth/user/create"),
        ("POST", "/auth/email/send_code"),
        ("DELETE", "/auth/user/delete/tech-42"),
    ]
