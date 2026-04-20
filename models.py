from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)

    # 關聯
    posts = relationship("Post", back_populates="owner")
    comments = relationship("Comment", back_populates="author")
    likes = relationship("Like", back_populates="user")
    
    # 黑名單關聯 (主動封鎖的人 vs 被封鎖的人)
    blocking = relationship("Blacklist", foreign_keys="Blacklist.blocker_id", back_populates="blocker")
    blocked_by = relationship("Blacklist", foreign_keys="Blacklist.blocked_id", back_populates="blocked")

class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    owner_id = Column(Integer, ForeignKey("users.id"))
    top_comment_id = Column(Integer, ForeignKey("comments.id", use_alter=True), nullable=True) # 置頂留言

    owner = relationship("User", back_populates="posts")
    comments = relationship("Comment", back_populates="post", foreign_keys="Comment.post_id")
    likes = relationship("Like", back_populates="post")

class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    post_id = Column(Integer, ForeignKey("posts.id"))
    author_id = Column(Integer, ForeignKey("users.id"))
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True) # 巢狀留言的關鍵：指向上一層留言

    post = relationship("Post", back_populates="comments", foreign_keys=[post_id])
    author = relationship("User", back_populates="comments")
    replies = relationship("Comment", backref="parent", remote_side=[id]) # 自身關聯 (Self-referential)
    likes = relationship("Like", back_populates="comment")

class Like(Base):
    __tablename__ = "likes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # 多態設計：一個讚可能屬於貼文，也可能屬於留言
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
    comment_id = Column(Integer, ForeignKey("comments.id"), nullable=True)

    user = relationship("User", back_populates="likes")
    post = relationship("Post", back_populates="likes")
    comment = relationship("Comment", back_populates="likes")

class Blacklist(Base):
    __tablename__ = "blacklists"

    id = Column(Integer, primary_key=True, index=True)
    blocker_id = Column(Integer, ForeignKey("users.id")) # 設定黑名單的人
    blocked_id = Column(Integer, ForeignKey("users.id")) # 被封鎖的人

    blocker = relationship("User", foreign_keys=[blocker_id], back_populates="blocking")
    blocked = relationship("User", foreign_keys=[blocked_id], back_populates="blocked_by")