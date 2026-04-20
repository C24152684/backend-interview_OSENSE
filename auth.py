from datetime import datetime, timedelta, timezone
from jose import jwt
from typing import Optional
from fastapi.security import OAuth2PasswordBearer

# =========================================================
# 🔑 JWT 設定
# =========================================================
SECRET_KEY = "your-secret-key-fastapi-demo"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# =========================================================
# 🔐 OAuth2 token 來源
# =========================================================
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# =========================================================
# 🔐 可選 token（未登入也不報錯）
# =========================================================
optional_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="login",
    auto_error=False
)

# =========================================================
# 🎟️ 產生 JWT token
# =========================================================
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()

    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
