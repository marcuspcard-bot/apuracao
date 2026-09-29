"""Supabase verifies credentials and bearer tokens; only explicit user IDs are admins."""

import httpx
from fastapi import HTTPException, Request
from app.core.config import get_settings


def auth_request(method: str, path: str, *, token: str = "", body=None):
    settings = get_settings()
    if (
        not settings.supabase_url
        or not settings.supabase_service_role_key
        or not settings.admin_user_ids
    ):
        raise HTTPException(503, "O acesso administrativo ainda não foi configurado.")
    headers = {"apikey": settings.supabase_service_role_key}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(timeout=10) as client:
            response = client.request(
                method,
                f"{settings.supabase_url.rstrip('/')}/auth/v1/{path}",
                headers=headers,
                json=body,
            )
    except httpx.RequestError:
        raise HTTPException(503, "Não foi possível validar o acesso. Tente novamente.") from None
    if response.status_code == 429:
        raise HTTPException(429, "Muitas tentativas. Aguarde antes de tentar novamente.")
    if response.status_code >= 500:
        raise HTTPException(503, "O serviço de autenticação está indisponível.")
    if response.status_code >= 400:
        raise HTTPException(
            401, "E-mail, senha ou sessão inválidos.", headers={"WWW-Authenticate": "Bearer"}
        )
    return response.json() if response.content else {}


def authorize_user(user):
    allowed = {part.strip() for part in get_settings().admin_user_ids.split(",") if part.strip()}
    if not user.get("id") or user["id"] not in allowed:
        raise HTTPException(403, "Este usuário não tem acesso administrativo.")
    return {"id": user["id"], "email": user.get("email", "")}


def bearer_token(request: Request):
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            401, "Entre com sua conta de administrador.", headers={"WWW-Authenticate": "Bearer"}
        )
    return token.strip()


def require_admin(request: Request):
    return authorize_user(auth_request("GET", "user", token=bearer_token(request)))
