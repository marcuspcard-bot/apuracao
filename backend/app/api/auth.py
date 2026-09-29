from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, SecretStr
from app.core.auth import auth_request, authorize_user, bearer_token, require_admin

router = APIRouter(prefix="/api/auth", tags=["Acesso"])


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=1024)


@router.post("/login")
def login(body: Login, response: Response):
    response.headers["Cache-Control"] = "no-store"
    data = auth_request(
        "POST",
        "token?grant_type=password",
        body={"email": body.email.strip(), "password": body.password.get_secret_value()},
    )
    user = authorize_user(data.get("user", {}))
    # Never forward refresh tokens, provider tokens or service credentials.
    return {"access_token": data["access_token"], "expires_in": data["expires_in"], "user": user}


@router.get("/me")
def me(response: Response, user=Depends(require_admin)):
    response.headers["Cache-Control"] = "no-store"
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, user=Depends(require_admin)):
    auth_request("POST", "logout?scope=local", token=bearer_token(request))
    response.headers["Cache-Control"] = "no-store"
