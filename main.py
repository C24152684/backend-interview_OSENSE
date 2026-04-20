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
from utils import get_optional_current_user, get_blocked_user_ids, serialize_comment



# 在啟動時自動建立資料庫表 (非同步方式)
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

@app.get("/")
async def root():
    return {"message": "API 伺服器運作中！"}

# 簡單的測試端點：檢查資料庫連線
@app.get("/test-db")
async def test_db(db: AsyncSession = Depends(get_db)):
    return {"status": "success", "db_session": str(db)}



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
async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(status_code=401, detail="Could not validate credentials")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    result = await db.execute(select(models.User).where(models.User.username == username))
    user = result.scalars().first()
    if user is None:
        raise credentials_exception
    return user

# 只有登入後才能看到的測試 API
@app.get("/users/me", response_model=schemas.UserOut)
async def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user



''' 加入 發布貼文 '''
# 1. 發布新貼文 (需要驗證當前使用者)
@app.post("/posts", response_model=schemas.PostOut)
async def create_post(
    post_data: schemas.PostCreate, 
    db: AsyncSession = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    new_post = models.Post(
        content=post_data.content,
        owner_id=current_user.id
    )
    db.add(new_post)
    await db.commit()
    await db.refresh(new_post)
    
    # 為了回傳給前端顯示，手動附加上 username
    new_post.username = current_user.username
    return new_post

# 2. 獲取所有貼文 (暫時不考慮黑名單，先求能跑通)
# 建立一個輔助函數來遞迴處理留言資料
def serialize_comment(comment, children_map):
    """
    將 SQLAlchemy Comment 轉成 Pydantic schema
    不使用 ORM 的 replies，改用 children_map 建立真正巢狀
    """
    return schemas.CommentOut(
        id=comment.id,
        content=comment.content,
        author_id=comment.author_id,
        author_name=comment.author.username if comment.author else "未知用戶",
        created_at=comment.created_at,
        like_count=len(comment.likes) if comment.likes else 0,
        parent_id=comment.parent_id,
        # ✅ 用 children_map 建 tree（關鍵）
        replies=[
            serialize_comment(child, children_map)
            for child in children_map.get(comment.id, [])
        ]
    )

@app.get("/posts", response_model=List[schemas.PostOut])
async def get_posts(db: AsyncSession = Depends(get_db)):
    # ✅ Eager loading（避免 N+1）
    query = select(models.Post).options(
        selectinload(models.Post.owner),
        selectinload(models.Post.likes),
        selectinload(models.Post.comments).selectinload(models.Comment.author),
        selectinload(models.Post.comments).selectinload(models.Comment.likes),
        # ⚠️ replies 其實可以拿掉（我們不用了）
        # selectinload(models.Post.comments).selectinload(models.Comment.replies)
    )
    
    result = await db.execute(query)
    posts = result.scalars().all()

    final_posts = []

    for post in posts:
        username = post.owner.username
        likes_count = len(post.likes)

        # 🔥 Step 1：建立 parent → children map
        children_map = {}
        for c in post.comments:
            if c.parent_id is not None:
                children_map.setdefault(c.parent_id, []).append(c)

        # 🔥 Step 2：只取 root comment
        root_comments = [
            serialize_comment(c, children_map)
            for c in post.comments
            if c.parent_id is None
        ]

        # ✅ 組裝輸出（完全不動 ORM）
        post_out = schemas.PostOut(
            id=post.id,
            content=post.content,
            created_at=post.created_at,
            owner_id=post.owner_id,
            username=username,
            likes_count=likes_count,
            comments=root_comments
        )

        final_posts.append(post_out)

    return final_posts



''' 加入 按讚、留言 '''
# 1. 發表留言 (支援巢狀)
@app.post("/posts/{post_id}/comments", response_model=schemas.CommentOut)
async def create_comment(
    post_id: int, 
    comment_data: schemas.CommentCreate, 
    db: AsyncSession = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    # 建立模型
    new_comment_obj = models.Comment(
        content=comment_data.content,
        post_id=post_id,
        author_id=current_user.id,
        parent_id=comment_data.parent_id
    )
    db.add(new_comment_obj)
    await db.commit()
    await db.refresh(new_comment_obj)
    
    # 關鍵：不要直接操作 new_comment_obj.replies
    # 我們改用 dict 的方式轉換，並補上 Pydantic 需要的欄位
    return schemas.CommentOut(
        id=new_comment_obj.id,
        content=new_comment_obj.content,
        author_id=new_comment_obj.author_id,
        author_name=current_user.username, # 直接拿當前使用者名字
        created_at=new_comment_obj.created_at,
        like_count=0,
        replies=[] # 這裡給空清單，完全不會觸發 SQLAlchemy 錯誤
    )

# 2. 按讚功能 (切換式：按一下讚，再按一下取消)
@app.post("/like/{target_type}/{target_id}")
async def toggle_like(
    target_type: str, # "post" 或 "comment"
    target_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 檢查是否按過讚
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


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)