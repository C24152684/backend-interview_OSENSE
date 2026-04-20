import uvicorn
import bcrypt   # 密碼加密
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from contextlib import asynccontextmanager      # FastAPI 改用 lifespan handlers 來管理應用程式生命週期

from jose import JWTError, jwt
from typing import List, Optional, Set # 新增 Set 用於快速比對 ID

import models
import schemas
from database import engine, Base, get_db
# from models import User
# from schemas import UserCreate, UserOut, Token, TokenData, PostCreate, PostOut
from auth import create_access_token, SECRET_KEY, ALGORITHM
from utils import get_optional_current_user, get_who_blocked_me, get_my_blacklist_ids, serialize_comment, sanitize_content



# =========================================================
# 🧱 初始化 DB
# 在啟動時自動建立資料庫表 (非同步方式)
# =========================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動：建立資料表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # App 運作期間：
    yield
    # 關閉：清空所有資料表（保留檔案但清空內容）
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.drop_all)

app = FastAPI(title="社群平台 API 測試", lifespan=lifespan)

# @app.get("/")
# async def root():
#     return {"message": "API 伺服器運作中！"}

# # 簡單的測試端點：檢查資料庫連線
# @app.get("/test-db")
# async def test_db(db: AsyncSession = Depends(get_db)):
#     return {"status": "success", "db_session": str(db)}



''' 加入註冊功能 '''
# 設定密碼雜湊加密
class PasswordHasher:
    @staticmethod
    def hash(password: str) -> str:
        # 將密碼轉為 bytes
        pwd_bytes = password.encode('utf-8')
        # 產生 salt 並雜湊
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(pwd_bytes, salt)
        return hashed.decode('utf-8')

    @staticmethod
    def verify(password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    
@app.post("/register", response_model=schemas.UserOut)
async def register(user_data: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    # 1. 檢查使用者是否已存在
    result = await db.execute(select(models.User).where(models.User.username == user_data.username))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # 2. 使用原生 bcrypt 加密 (解決 passlib 相容性問題)
    pwd_bytes = user_data.password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')
    
    new_user = models.User(username=user_data.username, password_hash=hashed_password)
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user



''' 加入登入 API '''
# 定義 Token 取得的位置
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

@app.post("/login", response_model=schemas.Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    # 1. 查找使用者
    result = await db.execute(select(models.User).where(models.User.username == form_data.username))
    user = result.scalars().first()
    
    # 2. 驗證密碼
    if not user or not bcrypt.checkpw(form_data.password.encode('utf-8'), user.password_hash.encode('utf-8')):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")

    # 3. 簽發 Token
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

# 建立一個輔助函數：獲取當前登入的使用者
async def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db),
    ):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")

        if not username:
            raise HTTPException(401, "invalid token")
        result = await db.execute(
            select(models.User).where(models.User.username == username)
        )

        user = result.scalars().first()
        if not user:
            raise HTTPException(401, "user not found")
        
        return user

    except JWTError:
        raise HTTPException(401, "invalid token")

# 只有登入後才能看到的測試 API
@app.get("/users/me", response_model=schemas.UserOut)
async def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user



''' 加入 發布貼文 '''
# =========================================================
# 📰 1. 發布新貼文 (需要驗證當前使用者)
# =========================================================
@app.post("/posts", response_model=schemas.PostOut)
async def create_post(
    post_data: schemas.PostCreate, 
    db: AsyncSession = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    # 將使用者輸入做安全處理
    clean_content = sanitize_content(post_data.content)
    if not clean_content.strip():
        raise HTTPException(status_code=400, detail="內容不可為空或是 HTML 等語法")

    new_post = models.Post(
        content=clean_content,   # DB: 只存「純文字」
        owner_id=current_user.id
    )
    db.add(new_post)
    await db.commit()
    await db.refresh(new_post)
    
    # response_model 完整輸出前端需要欄位
    return schemas.PostOut(
        id=new_post.id,
        content=new_post.content,
        created_at=new_post.created_at,
        owner_id=new_post.owner_id,
        username=current_user.username,
        likes_count=0,
        top_comment_id=None,
        comments=[]
    )


# =========================================================
# 🚫 2. 黑名單功能
# =========================================================
@app.post("/blacklist/{blocked_id}", response_model=schemas.BlacklistMessage)
async def toggle_blacklist(
    blocked_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    封鎖 / 解除封鎖切換 API
    """

    # ❌ 防止自己封鎖自己
    if blocked_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能封鎖自己")

    # 🔍 查是否已封鎖
    query = select(models.Blacklist).where(
        models.Blacklist.blocker_id == current_user.id,
        models.Blacklist.blocked_id == blocked_id
    )

    result = await db.execute(query)
    entry = result.scalars().first()

    # 🔁 如果存在 → 解除封鎖
    if entry:
        await db.delete(entry)
        await db.commit()
        return {
            "message": "已解除封鎖",
            "blocked_id": blocked_id,
            "is_blocked": False
        }

    # ➕ 不存在 → 新增封鎖
    new_block = models.Blacklist(
        blocker_id=current_user.id,
        blocked_id=blocked_id
    )

    db.add(new_block)
    await db.commit()

    return {
        "message": "已封鎖該使用者",
        "blocked_id": blocked_id,
        "is_blocked": True
    }


# =========================================================
# 📰 3. 獲取所有貼文（含黑名單過濾）
# =========================================================
@app.get("/posts", response_model=List[schemas.PostOut])
async def get_posts(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_optional_current_user)
):
    # 1. 取得封鎖我的人的 ID (這些人的貼文我不能看)
    blocked_by_ids = await get_who_blocked_me(db, current_user.id) if current_user else set()

    query = select(models.Post).options(
        selectinload(models.Post.owner),
        selectinload(models.Post.likes),
        selectinload(models.Post.comments).options(
            selectinload(models.Comment.author), # 預先載入留言作者
            selectinload(models.Comment.likes)   # 預先載入留言的按讚
        )
    )
    result = await db.execute(query)
    posts = result.scalars().all()

    final_posts = []
    for post in posts:
        # 🚫黑名單規則1：貼文作者如果封鎖了我，整篇貼文看不到
        if post.owner_id in blocked_by_ids:
            continue

        # 🚫黑名單規則2：貼文作者如果封鎖了我，整篇貼文看不到
        # 建立留言樹用的 parent -> children 對照表
        children_map = {}
        for c in post.comments:
            if c.parent_id is not None:
                children_map.setdefault(c.parent_id, []).append(c)

        # 過濾根留言
        root_comments = [
            serialize_comment(c, children_map, blocked_by_ids, schemas)
            for c in post.comments
            if c.parent_id is None and c.author_id not in blocked_by_ids
        ]

        final_posts.append(
            schemas.PostOut(
                id=post.id,
                content=post.content,
                created_at=post.created_at,
                owner_id=post.owner_id,
                username=post.owner.username,
                likes_count=len(post.likes),
                top_comment_id=post.top_comment_id,     # 置頂留言 id 欄位
                comments=root_comments
            )
        )
    return final_posts

# 新增：管理介面需要的 API
@app.get("/blacklist/me")
async def get_my_blacklist(db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # 查出「我主動封鎖了誰」
    query = select(models.User).join(models.Blacklist, models.User.id == models.Blacklist.blocked_id)\
            .where(models.Blacklist.blocker_id == current_user.id)
    result = await db.execute(query)
    return [{"id": u.id, "username": u.username} for u in result.scalars().all()]


''' 加入 按讚、留言 '''
# =========================================================
# 1. 發表留言 (支援巢狀、封鎖檢查)
# =========================================================
@app.post("/posts/{post_id}/comments", response_model=schemas.CommentOut)
async def create_comment(
    post_id: int, 
    comment_data: schemas.CommentCreate, 
    db: AsyncSession = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    # 1. 查找該貼文及其作者
    post_result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = post_result.scalars().first()
    if not post:
        raise HTTPException(404, "貼文不存在")

    # 2. 核心防呆：檢查貼文作者是否封鎖了我
    blocked_by_ids = await get_who_blocked_me(db, current_user.id)
    # my_blacklist_ids = await get_my_blacklist_ids(db, current_user.id)

    if post.owner_id in blocked_by_ids:
        raise HTTPException(status_code=403, detail="由於黑名單設定，你無法對此貼文留言")
    
    # 3. 檢查「父留言作者」是否封鎖我 (如果是回覆某人)
    if comment_data.parent_id:
        parent_result = await db.execute(select(models.Comment).where(models.Comment.id == comment_data.parent_id))
        parent_comment = parent_result.scalars().first()
        if parent_comment and parent_comment.author_id in blocked_by_ids:
            raise HTTPException(status_code=403, detail="由於黑名單設定，你無法回覆使用者")
    
    # 4. 將使用者輸入做安全處理
    clean_content = sanitize_content(comment_data.content)
    if not clean_content.strip():
        raise HTTPException(status_code=400, detail="內容不可為空或是 HTML 等語法")

    # 5. 建立 留言 OBJ 模型
    new_comment_obj = models.Comment(
        content=clean_content,   # DB: 只存「純文字」
        post_id=post_id,
        author_id=current_user.id,
        parent_id=comment_data.parent_id
    )
    db.add(new_comment_obj)
    await db.commit()
    await db.refresh(new_comment_obj)
    
    # 6. 發布：不要直接操作 new_comment_obj.replies，改用 dict 的方式轉換，並補上 Pydantic 需要的欄位
    return schemas.CommentOut(
        id=new_comment_obj.id,
        content=new_comment_obj.content,
        author_id=new_comment_obj.author_id,
        author_name=current_user.username, # 直接拿當前使用者名字
        created_at=new_comment_obj.created_at,
        like_count=0,
        replies=[] # 這裡給空清單，完全不會觸發 SQLAlchemy 錯誤
    )

# =========================================================
# 2. 按讚功能 (切換式：按一下讚，再按一下取消)
# =========================================================
@app.post("/like/{target_type}/{target_id}")
async def toggle_like(
    target_type: str, # "post" 或 "comment"
    target_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # --- 1. 查找目標物件及其作者 ---
    target_owner_id = None
    if target_type == "post":
        result = await db.execute(select(models.Post).where(models.Post.id == target_id))
        target_obj = result.scalars().first()
        if not target_obj:
            raise HTTPException(404, "貼文不存在")
        target_owner_id = target_obj.owner_id
    elif target_type == "comment":
        result = await db.execute(select(models.Comment).where(models.Comment.id == target_id))
        target_obj = result.scalars().first()
        if not target_obj:
            raise HTTPException(404, "留言不存在")
        target_owner_id = target_obj.author_id
    else:
        raise HTTPException(400, "無效的目標類型")

    # --- 2. 核心防呆：對方是否封鎖我 ---
    # 檢查：對方是否封鎖我
    blocked_by_ids = await get_who_blocked_me(db, current_user.id)
    # my_blacklist_ids = await get_my_blacklist_ids(db, current_user.id)
    if target_owner_id in blocked_by_ids:
        raise HTTPException(status_code=403, detail="由於黑名單設定，你無法按讚此內容")
    
    # --- 3. 檢查是否按過讚 ---
    filter_args = {"user_id": current_user.id}
    if target_type == "post":
        filter_args["post_id"] = target_id
    else:
        filter_args["comment_id"] = target_id
    
    query = select(models.Like).filter_by(**filter_args)
    result = await db.execute(query)
    existing_like = result.scalars().first()

    if existing_like:
        await db.delete(existing_like)
        message = "已取消讚"
    else:
        new_like = models.Like(**filter_args)
        db.add(new_like)
        message = "已按讚"
    
    await db.commit()
    return {"message": message}


# =========================================================
# 📌 4. 置頂留言功能
# =========================================================
''' 加入 至頂留言 '''
# 置頂 API
@app.post("/posts/{post_id}/top-comment/{comment_id}")
async def set_top_comment(
    post_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. 先找貼文
    result = await db.execute(
        select(models.Post).where(models.Post.id == post_id)
    )
    post = result.scalars().first()

    if not post:
        raise HTTPException(status_code=404, detail="貼文不存在")

    # 2. 只有貼文作者可以設定置頂留言
    if post.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="只有貼文作者可以設定置頂留言")

    # 3. 檢查留言是否存在，且必須屬於這篇貼文
    result = await db.execute(
        select(models.Comment).where(
            models.Comment.id == comment_id,
            models.Comment.post_id == post_id
        )
    )
    comment = result.scalars().first()

    if not comment:
        raise HTTPException(status_code=404, detail="留言不存在或不屬於這篇貼文")

    # 4. 設定置頂留言
    post.top_comment_id = comment_id
    await db.commit()

    return {
        "message": "已設定置頂留言",
        "post_id": post_id,
        "top_comment_id": comment_id
    }

# 取消置頂 API
@app.delete("/posts/{post_id}/top-comment")
async def clear_top_comment(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    result = await db.execute(
        select(models.Post).where(models.Post.id == post_id)
    )
    post = result.scalars().first()

    if not post:
        raise HTTPException(status_code=404, detail="貼文不存在")

    if post.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="只有貼文作者可以取消置頂留言")

    post.top_comment_id = None
    await db.commit()

    return {
        "message": "已取消置頂留言",
        "post_id": post_id
    }




if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)