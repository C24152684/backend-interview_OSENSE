import streamlit as st
import requests
import html
from textwrap import dedent



# =========================================================
# 工具函式
# =========================================================
def get_auth_headers():
    """
    依目前登入狀態組出 Bearer token headers
    """
    token = st.session_state.get("access_token")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}

def safe_api_error(resp, default_msg="操作失敗"):
    """
    盡量從 API response 取出 detail，取不到就回傳預設字串
    """
    try:
        data = resp.json()
        return data.get("detail") or data.get("message") or default_msg
    except Exception:
        return default_msg

def find_comment_by_id(comments, target_id):
    """
    遞迴搜尋整棵留言樹，找到指定 comment_id 的留言，用於顯示置頂留言
    """
    for cmt in comments:
        if cmt["id"] == target_id:
            return cmt
        replies = cmt.get("replies", [])
        if replies:
            found = find_comment_by_id(replies, target_id)
            if found:
                return found
    return None

def handle_403(resp):
    """
    統一處理後端回應 403：存訊息到 session_state
    """
    if resp.status_code == 403:
        try:
            msg = resp.json().get("detail", "存取被拒絕")
        except Exception:
            msg = "存取被拒絕"

        st.session_state.block_message = msg
        return True  # 表示已處理
    return False

@st.dialog("存取權限變更")
def show_block_dialog():
    msg = st.session_state.get("block_message", "存取被拒絕")

    st.warning(f"🚫 {msg}")
    st.write("頁面內容即將更新")

    if st.button("我知道了，重新整理"):
        st.session_state.block_message = None
        st.rerun()

def api_post(url, **kwargs):
    """
    包一層 requests.post + 統一 403 處理
    """
    resp = requests.post(url, **kwargs)
    if handle_403(resp):
        st.stop()  # 只在這裡中斷 UI flow
    return resp

def api_get(url, **kwargs):
    """
    包一層 requests.get + 統一 403 處理
    """
    resp = requests.get(url, **kwargs)
    if handle_403(resp):
        st.stop()
    return resp

def api_delete(url, **kwargs):
    """
    包一層 requests.delete + 統一 403 處理
    """
    resp = requests.delete(url, **kwargs)
    if handle_403(resp):
        st.stop()
    return resp



# 設定 API 基礎網址
API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="社群平台測試端", layout="centered")
st.title("🚀 社群平台開發測試介面")

# =========================================================
# 如果有 403 訊息 → 顯示 dialog
# =========================================================
if st.session_state.get("block_message"):
    show_block_dialog()

# =========================================================
# 初始化 Session State (儲存狀態) 
# =========================================================
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "username" not in st.session_state:
    st.session_state.username = None
if "user_id" not in st.session_state:   # 判斷「我是不是這篇貼文作者」
    st.session_state.user_id = None
if "block_message" not in st.session_state:   # 顯示「權限不足」狀態
    st.session_state.block_message = None



# =========================================================
# 遞迴顯示留言樹
#
# 參數說明：
# - comments: 目前這一層的留言 list
# - post_id: 貼文 ID
# - headers: requests headers（含 access token）
# - post_owner_id: 貼文作者 id，用來判斷誰能置頂
# - top_comment_id: 目前這篇貼文被置頂的留言 id
# - depth: 巢狀層級（root=0）
# - pinned_mode:
#     True  = 這棵樹是「上方置頂留言區」專用
#     False = 一般下方完整留言樹
# - skip_root_comment_id:
#     下方一般留言區略過已經在上方顯示過的 root 留言，避免重複
#     只會在 depth == 0 時生效
# =========================================================
def render_comments(
        comments,
        post_id,
        headers,
        post_owner_id,
        top_comment_id=None,
        depth=0,
        pinned_mode=False,
        skip_root_comment_id=None,
    ):
    current_user_id = st.session_state.get("user_id")
    is_post_owner = (current_user_id == post_owner_id)

    for cmt in comments:
        comment_id = cmt["id"]
        author_id = int(cmt["author_id"])
        author_name = cmt.get("author_name", "未知使用者")
        content = cmt.get("content", "")
        like_count = cmt.get("like_count", 0)
        replies = cmt.get("replies", [])
        has_replies = bool(replies)
        parent_id = cmt.get("parent_id")
        is_root = (parent_id is None)
        is_top_comment = (comment_id == top_comment_id)

        # 避免下方重複顯示置頂 root
        if (
            not pinned_mode
            and depth == 0
            and skip_root_comment_id is not None
            and comment_id == skip_root_comment_id
        ):
            continue

        # ---------- state ----------
        mode_tag = "pinned" if pinned_mode else "normal"
        expand_key = f"expand_{comment_id}_{mode_tag}"
        reply_key = f"reply_to_{comment_id}_{mode_tag}"
        input_key = f"reply_input_{comment_id}_{mode_tag}"

        st.session_state.setdefault(expand_key, False)
        st.session_state.setdefault(reply_key, False)

        # ---------- 安全處理 ----------
        safe_author_name = html.escape(str(author_name))
        safe_content = html.escape(str(content))

        # --- 核心排版修正 ---
        # 建立兩個欄位：第一個是縮排佔位，第二個是實際內容
        # depth * 0.05 代表每一層縮排 5% 的寬度，最高縮排 25% 避免內容太窄
        indent_width = min(depth * 0.05, 0.25)
        
        if indent_width > 0:
            spacer, main_content = st.columns([indent_width, 1 - indent_width])
        else:
            # 第一層不縮排
            # main_content = st.container()
            # 避免 Streamlit 內部 layout 會有不穩行為
            if indent_width > 0:
                spacer, main_content = st.columns([indent_width, 1 - indent_width])
            else:
                main_content = st

        # with main_content:
        # 避免 Streamlit 內部 layout 會有不穩行為
        with main_content.container():
            # 整個留言用一個 container 包起來，增加層次感
            with st.container(border=True):
                # 1. 作者與置頂標籤
                pin_badge_html = f'<span style="background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:10px;font-size:12px;margin-left:5px;">📌 置頂</span>' if is_top_comment and is_root else ""
                st.markdown(f"**{safe_author_name}** {pin_badge_html}", unsafe_allow_html=True)
                
                # 2. 內容
                st.write(content)

                # 3. 按鈕列 (減少 Column 數量，避免擠壓)
                # 欄位說明(可手動微調)：[按讚, 回覆, 收合/展開, 封鎖/解封鎖, 置頂, 預留空間]
                btn_cols = st.columns([0.15, 0.15, 0.2, 0.1, 0.25, 0.15])
                
                with btn_cols[0]:
                    if st.button(f"👍 {like_count}", key=f"lk_{comment_id}_{mode_tag}"):
                        # resp = api_post(f"{API_URL}/like/comment/{comment_id}", headers=headers)
                        # 新增：被封鎖則呼叫對話框
                        resp = api_post(f"{API_URL}/like/comment/{comment_id}", headers=headers)
                        st.rerun()
                
                with btn_cols[1]:
                    if st.button("回覆", key=f"re_{comment_id}_{mode_tag}"):
                        st.session_state[reply_key] = not st.session_state[reply_key]
                        st.rerun()

                with btn_cols[2]:
                    if has_replies:
                        btn_txt = "收合" if st.session_state[expand_key] else f"展開({len(replies)})"
                        if st.button(btn_txt, key=f"ex_{comment_id}_{mode_tag}"):
                            st.session_state[expand_key] = not st.session_state[expand_key]
                            st.rerun()
                
                with btn_cols[3]:
                    # 只有不是自己的留言才顯示檢舉/封鎖
                    # if current_user_id and author_id != current_user_id:
                    # 新增：封鎖後取消顯示按鈕
                    blocked_by_ids = st.session_state.get("blocked_by_ids", set())
                    if (
                        current_user_id
                        and author_id != current_user_id
                        and author_id not in blocked_by_ids   # 新增條件
                    ):
                        if st.button("🚫", key=f"blk_{comment_id}_{mode_tag}"):
                            api_post(f"{API_URL}/blacklist/{author_id}", headers=headers)
                            st.rerun()

                with btn_cols[4]:
                    # 置頂按鈕：文字長度較長，給多一點空間
                    if is_post_owner and is_root:
                        if is_top_comment:
                            if st.button("取消置頂", key=f"unp_{comment_id}_{mode_tag}"):
                                requests.delete(f"{API_URL}/posts/{post_id}/top-comment", headers=headers)
                                st.rerun()
                        else:
                            if st.button("設為置頂", key=f"pin_{comment_id}_{mode_tag}"):
                                api_post(f"{API_URL}/posts/{post_id}/top-comment/{comment_id}", headers=headers)
                                st.rerun()

            # 4. 回覆輸入框 (放在 container 內)
            if st.session_state.get(reply_key, False):
                with st.form(key=f"form_{comment_id}_{mode_tag}"):
                    reply_text = st.text_area("回覆內容")
                    if st.form_submit_button("送出"):
                        if reply_text.strip():
                            # resp = api_post(
                            #     f"{API_URL}/posts/{post_id}/comments", 
                            #     headers=headers, 
                            #     json={"content": reply_text, "parent_id": comment_id}
                            # )
                            # 新增：被封鎖則呼叫對話框
                            resp = api_post(
                                f"{API_URL}/posts/{post_id}/comments", 
                                headers=headers, 
                                json={"content": reply_text, "parent_id": comment_id}
                            )
                            st.session_state[reply_key] = False
                            st.rerun()

            # 5. 子留言遞迴 (必須在 main_content 裡面，這樣才會跟著縮排)
            if has_replies and st.session_state.get(expand_key, False):
                render_comments(
                    comments=replies,
                    post_id=post_id,
                    headers=headers,
                    post_owner_id=post_owner_id,
                    top_comment_id=top_comment_id,
                    depth=depth + 1,
                    pinned_mode=pinned_mode,
                    skip_root_comment_id=skip_root_comment_id
                )

# =========================================================
# 側邊欄：登入與註冊
# =========================================================
st.sidebar.header("🔑 使用者系統")

tab1, tab2 = st.sidebar.tabs(["登入", "註冊"])

with tab2:
    st.subheader("建立新帳號")
    reg_user = st.text_input("註冊帳號", key="reg_u")
    reg_pwd = st.text_input("註冊密碼", type="password", key="reg_p")
    if st.button("註冊"):
        resp = api_post(f"{API_URL}/register", json={"username": reg_user, "password": reg_pwd})
        if resp.status_code == 200:
            st.success("註冊成功！請切換至登入分頁。")
        else:
            st.error(f"註冊失敗: {resp.json().get('detail')}")

with tab1:
    st.subheader("登入系統")
    login_user = st.text_input("帳號", key="log_u")
    login_pwd = st.text_input("密碼", type="password", key="log_p")

    if st.button("登入"):
        # OAuth2 標準格式是用 form-data
        data = {"username": login_user, "password": login_pwd}
        # login 通常不應該進 403 handler flow，不應該 st.stop
        resp = requests.post(f"{API_URL}/login", data=data)

        if resp.status_code == 200:
            st.session_state.access_token = resp.json().get("access_token")
            st.session_state.username = login_user

            # 取得目前登入者資訊，保存 user_id
            headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
            me_resp = requests.get(f"{API_URL}/users/me", headers=headers)
            if me_resp.status_code == 200:
                me_data = me_resp.json()
                st.session_state.user_id = me_data["id"]

            st.success(f"歡迎回來, {login_user}!")
            st.rerun()
        else:
            st.error("登入失敗，請檢查帳密。")

    if st.session_state.access_token:
        if st.button("登出"):
            st.session_state.access_token = None
            st.session_state.username = None
            st.session_state.user_id = None     # 登出時一起清掉 user_id
            st.rerun()



# =========================================================
# 主畫面
# =========================================================
st.divider()

if not st.session_state.access_token:
    st.info("👈 請先從左側登入或註冊以開始測試功能。")
else:
    st.write(f"### 📍 當前身分：**{st.session_state.username}**")
    
    # 測試「我的資訊」API
    headers = {"Authorization": f"Bearer {st.session_state.access_token}"}

    # =========================================================
    # 🚫 黑名單管理區塊
    # 顯示「我目前封鎖了誰」，並提供解封鎖按鈕
    # 後端使用：
    # 1. GET  /blacklist/me         -> 取得黑名單列表
    # 2. POST /blacklist/{user_id}  -> 切換封鎖 / 解封鎖
    # =========================================================
    st.divider()
    st.subheader("🚫 黑名單管理")

    # 呼叫後端 API，取得目前登入者封鎖的人
    blacklist_resp = requests.get(f"{API_URL}/blacklist/me", headers=headers)

    if blacklist_resp.status_code == 200:
        blacklist_users = blacklist_resp.json()

        # 若黑名單為空
        if not blacklist_users:
            st.caption("目前沒有封鎖任何使用者")
        else:
            # 逐一列出被封鎖的使用者
            for user in blacklist_users:
                with st.container(border=True):
                    col1, col2 = st.columns([0.7, 0.3])

                    with col1:
                        st.write(f"@{user['username']}  (ID: {user['id']})")

                    with col2:
                        # 這裡一樣沿用你原本的 toggle blacklist API
                        # 因為對已封鎖的人再打一次，就會變成解除封鎖
                        if st.button("解封鎖", key=f"unblock_{user['id']}"):
                            unblock_resp = api_post(
                                f"{API_URL}/blacklist/{user['id']}",
                                headers=headers
                            )

                            if unblock_resp.status_code == 200:
                                st.success(f"已解除封鎖 @{user['username']}")
                                st.rerun()
                            else:
                                st.error("解封鎖失敗")
    else:
        st.error("黑名單資料讀取失敗")

    # =========================================================
    # 取得個人 id API 測試
    # =========================================================
    if st.button("取得 API 個人資訊測試"):
        resp = requests.get(f"{API_URL}/users/me", headers=headers)
        st.json(resp.json())

    # --- 發文功能 ---
    st.subheader("📝 發布新貼文")
    with st.form("post_form", clear_on_submit=True):
        content = st.text_area("想分享什麼？", placeholder="輸入貼文內容...")
        submit = st.form_submit_button("發布貼文")
        
        if submit:
            if content:
                resp = api_post(f"{API_URL}/posts", json={"content": content}, headers=headers)
                if resp.status_code == 200:
                    st.success("發布成功！")
                else:
                    st.error("發布失敗")
            else:
                st.warning("內容不能為空喔！")

    st.divider()

    # --- 貼文列表 ---
    st.subheader("🌍 貼文列表")
    
    # 先更新「誰封鎖我」：避免 blocked_by_ids 永遠是舊的
    blk_resp = requests.get(f"{API_URL}/blacklist/who_blocked_me", headers=headers)
    if blk_resp.status_code == 200:
        st.session_state.blocked_by_ids = set(map(int, blk_resp.json()))
    else:
        st.session_state.blocked_by_ids = set()

    # 再抓貼文
    posts_resp = requests.get(f"{API_URL}/posts", headers=headers)

    if posts_resp.status_code == 200:

        all_posts = posts_resp.json()
        if not all_posts:
            st.write("目前還沒有人發文喔～")

        # --- 貼文廣場部分 ---
        for p in reversed(all_posts):
            with st.container(border=True):
                st.markdown(f"**{p['username']}** · <small>{p['created_at'][:16]}</small>", unsafe_allow_html=True)
                st.write(p['content'])
                
                # --- 貼文按讚按鈕顯示數量 ---
                # 在 session_state 存了當前使用者的 id 來判斷是否點過讚
                likes_count = p.get('likes_count', 0)
                if st.button(f"👍 {likes_count} 人按讚", key=f"lk_p_{p['id']}"):
                    # resp = api_post(f"{API_URL}/like/post/{p['id']}", headers=headers)
                    # 新增：被封鎖則呼叫對話框
                    resp = api_post(f"{API_URL}/like/post/{p['id']}", headers=headers)
                    st.rerun()

                st.divider()
                st.write("💬 留言區")
                
                # =========================================================
                # 📌 顯示置頂留言區塊
                # 規則：
                # 1. 若這篇貼文有 top_comment_id，先從整棵留言樹找出那則留言
                # 2. 找到後，在留言列表上方先額外 render_comments() 顯示一個「置頂留言」區塊
                # 3. 下方 render_comments() 還是照常顯示完整留言樹
                # =========================================================
                top_comment = None
                if p.get("top_comment_id") and "comments" in p and p["comments"]:
                    top_comment = find_comment_by_id(
                        p["comments"],
                        p["top_comment_id"]
                    )

                if top_comment:
                    st.info("📌 置頂留言")

                    render_comments(
                        comments=[top_comment],
                        post_id=p["id"],
                        headers=headers,
                        post_owner_id=p["owner_id"],
                        top_comment_id=p.get("top_comment_id"),
                        depth=0,
                        pinned_mode=True,                 # 表示這是上方置頂區
                        skip_root_comment_id=None,        # 上方不要略過
                    )

                # =========================================================
                # 💬 顯示一般留言樹
                # 如果有置頂 root 留言，就略過它，避免重複
                # =========================================================
                if "comments" in p and p["comments"]:
                    render_comments(
                        comments=p.get("comments", []),
                        post_id=p["id"],
                        headers=headers,
                        post_owner_id=p["owner_id"],
                        top_comment_id=p.get("top_comment_id"),
                        depth=0,
                        pinned_mode=False,
                        skip_root_comment_id=p.get("top_comment_id"),   # 下方略過已置頂 root
                    )
                else:
                    st.caption("尚無留言")
                    
                # root 級留言輸入
                with st.expander("寫下你的留言..."):
                    with st.form(f"root_cmt_{p['id']}"):
                        new_cmt = st.text_input("留言內容")
                        if st.form_submit_button("留言"):
                            # resp = api_post(
                            #     f"{API_URL}/posts/{p['id']}/comments",
                            #     json={"content": new_cmt},
                            #     headers=headers
                            #     )
                            # 新增：被封鎖則呼叫對話框
                            resp = api_post(
                                f"{API_URL}/posts/{p['id']}/comments",
                                json={"content": new_cmt},
                                headers=headers
                                )
                            st.rerun()