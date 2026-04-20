from typing import Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import Depends, HTTPException
from jose import jwt, JWTError
import bleach   # 

import models
from database import get_db
from auth import SECRET_KEY, ALGORITHM, optional_oauth2_scheme



# =========================================================
# 🔐 可選登入解析
# 用途：未登入也能看 /posts
# =========================================================
async def get_optional_current_user(
    # 這裡要加上 Depends，FastAPI 才知道要從 Header 抓 Token
    token: Optional[str] = Depends(optional_oauth2_scheme),
    # 這裡也要加上 Depends，FastAPI 才知道要從 get_db 抓資料庫連線
    db: AsyncSession = Depends(get_db),
) -> Optional[models.User]:
    """
    ✔ 有 token -> 回傳 user 物件
    ✔ 沒 token 或 token 壞掉 -> 回傳 None (不報錯)
    """
    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")

        if not username:
            return None

        result = await db.execute(
            select(models.User).where(models.User.username == username)
        )
        return result.scalars().first()

    except Exception:
        return None


# =========================================================
# 🚫 黑名單查詢工具
# =========================================================
async def get_who_blocked_me(db: AsyncSession, user_id: int) -> Set[int]:
    """取得『封鎖我的人』的 ID 清單 (讓我看不見他們)"""
    query = select(models.Blacklist.blocker_id).where(
        models.Blacklist.blocked_id == user_id
    )
    result = await db.execute(query)
    return set(result.scalars().all())

async def get_my_blacklist_ids(db: AsyncSession, user_id: int) -> Set[int]:
    """取得『我封鎖的人』的 ID 清單 (讓他們看不見我)"""
    query = select(models.Blacklist.blocked_id).where(
        models.Blacklist.blocker_id == user_id
    )
    result = await db.execute(query)
    return set(result.scalars().all())


# ========================================================= 
# 🌳 Comment Tree 建構（增加過濾功能）
# 建立一個輔助函數來遞迴處理留言資料
# =========================================================
def serialize_comment(
    comment,
    children_map,
    blocked_by_ids: Set[int],     # 傳入封鎖我的人的 ID 清單
    schemas
):
    """
    將 Comment ORM → CommentOut + 遞迴 tree
    並遞迴建立 tree structure
    """
    # 如果留言作者封鎖了我，遞迴時直接忽略該留言 (雖然在 main.py 已過濾第一層，但這層保護子留言)
    replies = []
    if comment.id in children_map:
        for child in children_map[comment.id]:
            # =================================================
            # 🔥 核心：遞迴建立留言樹 + 黑名單過濾
            # =================================================
            if child.author_id not in blocked_by_ids:
                replies.append(serialize_comment(child, children_map, blocked_by_ids, schemas))

    return schemas.CommentOut(
        id=comment.id,
        content=comment.content,
        author_id=comment.author_id,

        # 👉 防止 author 被刪或 null
        author_name=(
            comment.author.username
            if comment.author
            else "未知用戶"
        ),

        created_at=comment.created_at,

        # 👉 like 數量（避免 None crash）
        like_count=len(comment.likes or []),

        parent_id=comment.parent_id,

        # =================================================
        # 🔥 核心：遞迴建立留言樹 + 黑名單過濾
        # =================================================
        replies=replies
    )


# =========================================================
# 🧼 安全處理：過濾使用者輸入（防止 HTML / XSS）
# =========================================================
def sanitize_content(content: str) -> str:
    """
    將使用者輸入轉為「純文字」
    - 移除所有 HTML tag
    - 防止 XSS 攻擊
    - 確保 DB 不會被污染
    """
    return bleach.clean(
        content,
        tags=[],          # ❌ 不允許任何 HTML tag
        attributes={},    # ❌ 不允許任何屬性
        strip=True        # ✅ 直接移除 tag（不是 escape）
    )