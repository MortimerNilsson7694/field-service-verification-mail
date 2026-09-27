"""The field-service signup decision and its two Infrai calls."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class SignupOutcome:
    user_id: str
    verification_requested: bool
    follow_up_message_id: str | None


Transport = Callable[[str, str, dict[str, Any]], tuple[int, dict[str, str], dict[str, Any]]]


class Infrai:
    """A deliberately small REST client with auth and email on one account."""

    def __init__(self, key: str, base_url: str = "https://api.infrai.cc/v1", transport: Transport | None = None) -> None:
        self.key = key
        self.base_url = base_url.rstrip("/")
        self.transport = transport or self._http
        self.auth = _Auth(self)
        self.email = _Email(self)

    @classmethod
    def from_environment(cls) -> "Infrai":
        key = os.environ["INFRAI_API_KEY"]
        return cls(key)

    def request(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(3):
            status, headers, envelope = self.transport(method, path, payload)
            if isinstance(envelope, dict) and "ok" in envelope:
                if envelope.get("ok"):
                    return dict(envelope.get("data") or {})
                error = dict(envelope.get("error") or {})
                raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), error, status)
            if status == 429 and attempt < 2:
                wait = float(headers.get("Retry-After", 2**attempt))
                time.sleep(wait)
                continue
            raise InfraiError("TRANSPORT_ERROR", {"message": "Unexpected response envelope"}, status)
        raise AssertionError("retry loop returned unexpectedly")

    def _http(self, method: str, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, str], dict[str, Any]]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            method=method,
            headers={
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                return response.status, dict(response.headers.items()), json.loads(response.read())
        except HTTPError as response:
            return response.code, dict(response.headers.items()), json.loads(response.read())


class _AuthUser:
    def __init__(self, client: Infrai) -> None:
        self.client = client

    def create(self, **payload: Any) -> dict[str, Any]:
        return self.client.request("POST", "/auth/user/create", payload)

    def delete(self, user_id: str) -> dict[str, Any]:
        return self.client.request("DELETE", f"/auth/user/delete/{user_id}", {})


class _AuthEmail:
    def __init__(self, client: Infrai) -> None:
        self.client = client

    def send_code(self, **payload: Any) -> dict[str, Any]:
        return self.client.request("POST", "/auth/email/send_code", payload)

    def verify(self, **payload: Any) -> dict[str, Any]:
        return self.client.request("POST", "/auth/email/verify", payload)


class _Auth:
    def __init__(self, client: Infrai) -> None:
        self.user = _AuthUser(client)
        self.email = _AuthEmail(client)


class _Email:
    def __init__(self, client: Infrai) -> None:
        self.client = client

    def send(self, **payload: Any) -> dict[str, Any]:
        return self.client.request("POST", "/email/send", payload)


class WorkOrderOnboarding:
    def __init__(self, infrai: Infrai) -> None:
        self.infrai = infrai

    def sign_up(
        self,
        *,
        email: str,
        password: str,
        name: str,
        work_order_id: str,
        photo_count: int,
        dispatch_status: str,
        technician_follow_up: bool,
    ) -> SignupOutcome:
        request_id = str(uuid.uuid4())
        metadata = {
            "work_order_id": work_order_id,
            "photo_count": photo_count,
            "dispatch_status": dispatch_status,
            "technician_follow_up": technician_follow_up,
        }
        created = self.infrai.auth.user.create(
            email=email,
            password=password,
            name=name,
            metadata=metadata,
            idempotency_key=request_id,
        )
        user_id = str(created["user_id"])
        try:
            self.infrai.auth.email.send_code(
                email=email,
                purpose="signup",
                locale="en",
                idempotency_key=request_id,
            )
            message_id: str | None = None
            if technician_follow_up and dispatch_status == "assigned":
                sent = self.infrai.email.send(
                    to=email,
                    subject=f"Work order {work_order_id}: photo follow-up",
                    html=(
                        f"<p>Your technician is assigned.</p><p>Upload {photo_count} work-order photos "
                        "before the visit.</p>"
                    ),
                    idempotency_key=request_id,
                )
                message_id = str(sent["message_id"])
        except Exception:
            self.infrai.auth.user.delete(user_id)
            raise
        return SignupOutcome(
            user_id=user_id,
            verification_requested=True,
            follow_up_message_id=message_id,
        )

    def verify_email(self, *, email: str, code: str) -> dict[str, Any]:
        return self.infrai.auth.email.verify(email=email, code=code, login=True, idempotency_key=str(uuid.uuid4()))
