from fastapi import HTTPException

ADMIN_ID = "00000000-0000-0000-0000-000000000001"
TOKEN = "isolated-test-admin-token"


def fake_auth_request(method, path, *, token="", body=None):
    if path == "token?grant_type=password":
        if body != {"email": "admin@example.test", "password": "test-password"}:
            raise HTTPException(401, "E-mail, senha ou sessão inválidos.")
        return {
            "access_token": TOKEN,
            "expires_in": 3600,
            "user": {"id": ADMIN_ID, "email": body["email"]},
        }
    if token != TOKEN:
        raise HTTPException(401, "Sessão inválida.")
    return {"id": ADMIN_ID, "email": "admin@example.test"} if path == "user" else {}
