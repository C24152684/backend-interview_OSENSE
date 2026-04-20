# Simple Social Platform API (FastAPI)

本專案是依照 OsenseTech Backend 面試題所實作的一個簡易社群平台後端 API，包含使用者註冊 / 登入、貼文發佈、巢狀留言、按讚、置頂留言與黑名單等功能，後端使用 Python + FastAPI + async SQLAlchemy，並搭配一個簡易的 Streamlit 前端測試介面。

---

## 功能總覽

- 使用者系統
  - 註冊：`POST /register`
  - 登入取得 JWT：`POST /login`（OAuth2 form-data）
  - 取得目前登入者資訊：`GET /users/me`
- 發文功能
  - 建立貼文：`POST /posts`
  - 取得所有貼文：`GET /posts`
- 巢狀留言與互動
  - 對貼文留言（支援巢狀）：`POST /posts/{post_id}/comments`
  - 對貼文按讚：`POST /like/post/{post_id}`
  - 對留言按讚：`POST /like/comment/{comment_id}`
  - 置頂留言（僅貼文作者可操作）：
    - 設定：`POST /posts/{post_id}/top-comment/{comment_id}`
    - 取消：`DELETE /posts/{post_id}/top-comment`
- 黑名單功能
  - 封鎖 / 解除封鎖其他使用者：`POST /blacklist/{blocked_id}`
  - 查詢「我封鎖了誰」：`GET /blacklist/me`
  - 查詢「誰封鎖了我」：`GET /blacklist/who_blocked_me`
  - 被加入黑名單的使用者無法看到封鎖者的貼文，也無法對封鎖者的貼文或留言按讚 / 留言

---

## 架構

- 語言與框架
  - Python 3.12+
  - FastAPI（async/await 非同步方式實作）
- 驗證
  - OAuth2 + Password flow
- 資料庫
  - SQLite（會產生檔案 `social_platform.db`）
- 主要資料表（models）
  - `User`：使用者帳號與密碼 hash（bcrypt）
  - `Post`：貼文內容、作者與置頂留言 ID（`top_comment_id`）
  - `Comment`：巢狀留言（`parent_id` 指向自身）、作者、建立時間
  - `Like`：對貼文或留言的按讚（`post_id` 或 `comment_id` 任一不為空）
  - `Blacklist`：封鎖關係（`blocker_id` 封鎖 `blocked_id`）
- 前端測試介面
  - Streamlit：透過 REST API 呼叫上述後端服務

---

## 專案結構

```text
.
├── main.py         # FastAPI 入口，定義所有 API route
├── models.py       # SQLAlchemy ORM models
├── schemas.py      # Pydantic 模型 (Request / Response)
├── database.py     # Async engine / Session / Base 設定
├── auth.py         # JWT 與 OAuth2 設定
├── utils.py        # 黑名單查詢、巢狀留言序列化
└── frontend.py     # Streamlit 前端測試介面
```

---

## 環境準備與安裝

### 1. 建立虛擬環境（Python 3.12）
```bash
# Windows
python -m venv env
env\Scripts\activate

# macOS / Linux
python3 -m venv env
source env/bin/activate
```

### 2. 安裝相依套件
安裝 `requirements.txt`：
```bash
pip install -r requirements.txt
```

---

## 啟動後端 API 伺服器

### 執行 main.py

`main.py` 最下方已包含 `uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)`，可直接執行：

```bash
python main.py
```

---

## 啟動 Streamlit 前端測試介面

專案提供一個簡單的 Streamlit 前端，預設會連到 `http://127.0.0.1:8000` 的後端 API。

1. 確認後端 API 已經在 `http://127.0.0.1:8000` 以 `main:app` 跑起來。
2. 在同一個虛擬環境下執行：
   ```bash
   streamlit run frontend.py
   ```

3. 瀏覽器預設會開啟 `http://localhost:8501`，可以：
   - 左側登入 / 註冊（呼叫 `/register` 與 `/login`）
   - 發布貼文（呼叫 `POST /posts`）
   - 對貼文按讚 / 留言（呼叫 `POST /like/post/{id}` 和 `POST /posts/{id}/comments`）
   - 對留言按讚 / 回覆、置頂留言（呼叫 `POST /like/comment/{id}`、`POST /posts/{post_id}/top-comment/{comment_id}`）
   - 在黑名單管理區塊操作封鎖 / 解封鎖（對應 `GET /blacklist/me` 和 `POST /blacklist/{user_id}`）

---

## API 測試流程說明（Without UI）

除了使用 Streamlit，也可以用 curl 或任何 REST client（如 Postman、HTTPie）測試 API。

### 1. 註冊帳號

```bash
curl -X POST http://127.0.0.1:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username": "CY", "password": "123"}'
```

成功會回傳類似：

```json
{
  "id": 1,
  "username": "CY"
}
```

### 2. 登入取得 access token

```bash
curl -X POST http://127.0.0.1:8000/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=CY&password=123"
```

回傳：

```json
{
  "access_token": "<JWT_TOKEN>",
  "token_type": "bearer"
}
```

把 `<JWT_TOKEN>` 記下來，後面都會放在 `Authorization: Bearer ...` header 中。

### 3. 建立貼文

```bash
TOKEN="<JWT_TOKEN>"

curl -X POST http://127.0.0.1:8000/posts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello FastAPI!"}'
```

成功會回傳包含 `id`, `content`, `created_at`, `owner_id`, `username`, `likes_count`, `comments` 等欄位。

### 4. 取得貼文列表（不登入也可）

```bash
curl http://127.0.0.1:8000/posts
```

若你有登入並帶 token，後端會依黑名單規則過濾「封鎖你的使用者」之貼文，並組裝好巢狀留言樹與按讚數。

### 5. 對貼文留言 / 巢狀留言

假設貼文 ID 為 1：

```bash
# root level 留言
curl -X POST http://127.0.0.1:8000/posts/1/comments \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "第一層留言"}'
```

若要針對某留言再回覆（巢狀），假設 parent comment ID 為 10：

```bash
curl -X POST http://127.0.0.1:8000/posts/1/comments \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "回覆留言 10", "parent_id": 10}'
```

後端會根據 `parent_id` 建立 Comment Tree，並在 `GET /posts` 時以遞迴方式輸出 `[replies]` 巢狀結構。

### 6. 對貼文 / 留言按讚（Toggle）

- 對貼文 ID 1 按讚或取消讚：

```bash
curl -X POST http://127.0.0.1:8000/like/post/1 \
  -H "Authorization: Bearer $TOKEN"
```

- 對留言 ID 10 按讚或取消讚：

```bash
curl -X POST http://127.0.0.1:8000/like/comment/10 \
  -H "Authorization: Bearer $TOKEN"
```

後端會檢查 Like 是否已存在，存在則刪除（取消讚），不存在則新增（按讚），並回傳 `"已按讚"` 或 `"已取消讚"` 訊息。[file:1][file:5]

### 7. 置頂留言

僅貼文作者可以操作此功能。[file:1]

```bash
# 將留言 10 設為貼文 1 的置頂留言
curl -X POST http://127.0.0.1:8000/posts/1/top-comment/10 \
  -H "Authorization: Bearer $TOKEN"

# 取消置頂
curl -X DELETE http://127.0.0.1:8000/posts/1/top-comment \
  -H "Authorization: Bearer $TOKEN"
```

### 8. 黑名單操作與效果

- 封鎖 / 解封鎖 user_id = 2（toggle）：

```bash
curl -X POST http://127.0.0.1:8000/blacklist/2 \
  -H "Authorization: Bearer $TOKEN"
```

- 查詢我目前封鎖的所有使用者：

```bash
curl http://127.0.0.1:8000/blacklist/me \
  -H "Authorization: Bearer $TOKEN"
```

當 A 封鎖 B 時，資料表 `blacklists` 中會記錄一筆 `blocker_id = A.id, blocked_id = B.id`。[file:5]  
之後只要 B 嘗試瀏覽或互動，後端會透過 `get_who_blocked_me()` 取得「封鎖我的人」，並依規則做以下限制：[file:1][file:7]

- B 在 `GET /posts` 不會看到 A 的貼文
- B 嘗試對 A 的貼文留言 / 按讚，會得到 403
- B 嘗試對由 A 發佈的留言按讚或回覆，同樣會被拒絕（403）

---

## 注意事項

- 資料庫目前使用本機 SQLite 檔案 `social_platform.db`，若要改用其他 RDB（如 PostgreSQL），只需修改 `database.py` 中的連線字串與 driver，即可沿用同一套 async ORM 邏輯。
- 所有 API 路由皆以 `async def` 實作，並使用 `AsyncSession` 進行非同步資料庫操作，以符合題目「必須採用 async/await 非同步方式實作 API」的要求。