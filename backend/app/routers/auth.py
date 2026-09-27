"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.auth.dependencies import CurrentAuth, DbSession
from app.middleware.rate_limit import (
    client_ip,
    enforce_login_rate_limit,
    enforce_password_reset_rate_limit,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    CurrentUser,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
)
from app.schemas.common import ApiResponse, error_responses, ok
from app.schemas.system import ForgotPasswordRequest, ResetPasswordRequest
from app.services import presenters
from app.services.auth_service import RESET_REQUESTED, AuthService
from app.services.email import send_email

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/forgot-password",
    summary="Email a password reset link",
    description="Always returns the same response, whether or not the address has an account. "
    "The link expires after PASSWORD_RESET_EXPIRE_MINUTES and works once.",
    response_model=ApiResponse[None],
    responses=error_responses(422, 429),
    dependencies=[Depends(enforce_password_reset_rate_limit)],
)
def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
) -> dict:
    message = AuthService(db).request_password_reset(body.email, ip=client_ip(request))
    if message is not None:
        # Sent after the response so delivery time cannot reveal whether the account exists.
        background.add_task(send_email, message)
    return ok(None, RESET_REQUESTED)


@router.post(
    "/reset-password",
    summary="Set a new password using an emailed reset token",
    description="Ends every existing session of the account.",
    response_model=ApiResponse[None],
    responses=error_responses(400, 422, 429),
    dependencies=[Depends(enforce_password_reset_rate_limit)],
)
def reset_password(body: ResetPasswordRequest, db: DbSession) -> dict:
    AuthService(db).reset_password(body.token, body.new_password)
    return ok(None, "Password has been reset. You can now log in with the new password.")


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.post(
    "/login",
    summary="Log in with email or username",
    response_model=ApiResponse[LoginResponse],
    responses=error_responses(401, 403, 422, 429),
    dependencies=[Depends(enforce_login_rate_limit)],
)
def login(body: LoginRequest, request: Request, db: DbSession) -> dict:
    data = AuthService(db).login(
        body.identifier, body.password, ip=client_ip(request), user_agent=_ua(request)
    )
    return ok(data, "Login successful")


@router.post(
    "/refresh",
    summary="Exchange a refresh token for a new token pair",
    description="The submitted refresh token is revoked (rotation). Re-using it later is treated "
    "as theft and ends every session of that user.",
    response_model=ApiResponse[TokenPair],
    responses=error_responses(401, 422),
)
def refresh(body: RefreshRequest, request: Request, db: DbSession) -> dict:
    data = AuthService(db).refresh(
        body.refresh_token, ip=client_ip(request), user_agent=_ua(request)
    )
    return ok(data, "Token refreshed")


@router.post(
    "/logout",
    summary="Log out",
    description="Revokes the current access token and, if supplied, the refresh token. "
    "With all_devices=true every session of the user ends.",
    response_model=ApiResponse[None],
    responses=error_responses(401, 422),
)
def logout(ctx: CurrentAuth, db: DbSession, body: LogoutRequest | None = None) -> dict:
    body = body or LogoutRequest()
    AuthService(db).logout(ctx, body.refresh_token, body.all_devices)
    return ok(None, "Logged out from all devices" if body.all_devices else "Logged out")


@router.get(
    "/me",
    summary="Current user, roles and effective permissions",
    response_model=ApiResponse[CurrentUser],
    responses=error_responses(401),
)
def me(ctx: CurrentAuth) -> dict:
    return ok(presenters.current_user(ctx.user), "Current user")


@router.post(
    "/change-password",
    summary="Change your own password",
    description="Ends every other session and returns a fresh token pair for this one.",
    response_model=ApiResponse[TokenPair],
    responses=error_responses(400, 401, 422),
)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    ctx: CurrentAuth,
    db: DbSession,
) -> dict:
    data = AuthService(db).change_password(
        ctx,
        body.current_password,
        body.new_password,
        ip=client_ip(request),
        user_agent=_ua(request),
    )
    return ok(data, "Password changed successfully")
