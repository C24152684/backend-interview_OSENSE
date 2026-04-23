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
    echo=False,                                 # 將程式執行的 SQL 印在終端機上
    connect_args={"check_same_thread": False}   # 允許不同的執行緒共用同一個資料庫連線
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False     # 非同步環境下，防止在 commit 之後，還想讀取物件屬性
)

Base = declarative_base()

# 取得資料庫 Session 的依賴函數 (Dependency)
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session