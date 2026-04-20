from __future__ import annotations # 支援型別自我引用
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from typing import List


# 註冊、登入：資料模型
class UserCreate(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True # 讓 Pydantic 可以讀取 SQLAlchemy 模型


# login：定義 Token 的回傳格式
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None


# 發布貼文：
class PostCreate(BaseModel):
    content: str

class PostOut(BaseModel):
    id: int
    content: str
    created_at: datetime
    owner_id: int
    username: str                   # 額外傳出名字，方便前端顯示
    likes_count: int                # 新增按讚數
    # comments: List[CommentOut] = [] # 留言列表
    comments: List[CommentOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


# 巢狀留言與按讚：
class CommentCreate(BaseModel):
    content: str
    parent_id: Optional[int] = None # 如果是回覆留言，就帶上父留言 ID

# CommentOut.replies 欄位引用自己（巢狀結構）
class CommentOut(BaseModel):
    id: int
    content: str
    author_id: int
    author_name: str
    created_at: datetime
    like_count: int
    parent_id: Optional[int] = None
    # replies: List[CommentOut] = [] # 巢狀回覆列表
    replies: List[CommentOut] = Field(default_factory=list)

    class Config:
        from_attributes = True

# 必須在類別定義後執行，讓 Pydantic 處理遞迴參考
CommentOut.model_rebuild()

class PostDetailOut(PostOut):
    likes_count: int
    comments: List[CommentOut]


# 黑名單：封鎖功能的回傳訊息
class BlacklistMessage(BaseModel):
    message: str
    blocked_id: int
    is_blocked: bool