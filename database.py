from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

#[DB：存檔案 \ 存 RAM]=>
# 使用 SQLite 的非同步驅動
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./social_platform.db"
# # 使用記憶體資料庫
# SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
#<=[資料只存在 RAM] 

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL, 
    echo=True, # 開發階段設為 True 可以看 SQL 語法，提交前建議改為 False
    connect_args={"check_same_thread": False} 
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

# 取得資料庫 Session 的依賴函數 (Dependency)
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session