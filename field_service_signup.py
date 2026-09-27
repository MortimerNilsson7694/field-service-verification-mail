"""Run the field-service verification API with: uvicorn field_service_signup:app --reload."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr, Field

from work_order_onboarding import Infrai, InfraiError, WorkOrderOnboarding


app = FastAPI(title="Field-service verification")


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str
    work_order_id: str
    photo_count: int = Field(ge=0)
    dispatch_status: str
    technician_follow_up: bool


class VerifyRequest(BaseModel):
    email: EmailStr
    code: str


def service() -> WorkOrderOnboarding:
    return WorkOrderOnboarding(Infrai.from_environment())


@app.post("/signup")
def signup(request: SignupRequest) -> dict[str, object]:
    try:
        result = service().sign_up(**request.model_dump())
        return {
            "user_id": result.user_id,
            "verification_requested": result.verification_requested,
            "follow_up_message_id": result.follow_up_message_id,
        }
    except InfraiError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@app.post("/verification")
def verification(request: VerifyRequest) -> dict[str, object]:
    try:
        return service().verify_email(**request.model_dump())
    except InfraiError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
