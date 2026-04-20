import streamlit as st
import requests

# 設定 API 基礎網址
API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="社群平台測試端", layout="centered")
st.title("🚀 社群平台開發測試介面")

# --- 初始化 Session State (儲存登入狀態) ---
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "username" not in st.session_state:
    st.session_state.username = None

# --- 側邊欄：登入與註冊 ---
st.sidebar.header("🔑 使用者系統")

tab1, tab2 = st.sidebar.tabs(["登入", "註冊"])

with tab2:
    st.subheader("建立新帳號")
    reg_user = st.text_input("註冊帳號", key="reg_u")
    reg_pwd = st.text_input("註冊密碼", type="password", key="reg_p")
    if st.button("註冊"):
        resp = requests.post(f"{API_URL}/register", json={"username": reg_user, "password": reg_pwd})
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
        resp = requests.post(f"{API_URL}/login", data=data)
        if resp.status_code == 200:
            st.session_state.access_token = resp.json().get("access_token")
            st.session_state.username = login_user
            st.success(f"歡迎回來, {login_user}!")
            st.rerun()
        else:
            st.error("登入失敗，請檢查帳密。")

    if st.session_state.access_token:
        if st.button("登出"):
            st.session_state.access_token = None
            st.session_state.username = None
            st.rerun()


# 在 frontend.py 頂部定義遞迴顯示留言的函數
def render_comments(comments, post_id, headers, depth=0):
    for cmt in comments:
        comment_id = cmt['id']

        # =========================
        # 1️⃣ 初始化 state（預設收合）
        # =========================
        expand_key = f"expand_{comment_id}"
        reply_key = f"reply_to_{comment_id}"

        st.session_state.setdefault(expand_key, False)

        has_replies = bool(cmt.get('replies'))

        # =========================
        # 2️⃣ 留言 UI
        # =========================
        with st.container():

            # 留言本體（含縮排）
            st.markdown(
                f"""
                <div style="
                    border-left: 3px solid #ccc;
                    margin-left: {depth * 20}px;
                    padding-left: 10px;
                    margin-top: 8px;
                ">
                    <b>{cmt['author_name']}</b><br>
                    {cmt['content']}
                </div>
                """,
                unsafe_allow_html=True
            )

            # =========================
            # 3️⃣ 按鈕列（與留言同縮排視覺）
            # =========================
            cols = st.columns([depth * 0.05 + 0.05, 0.2, 0.2, 0.2, 0.35])

            # -------------------------
            # 👍 Like（樂觀更新）
            # -------------------------
            if cols[1].button(
                f"👍 {cmt.get('like_count', 0)}",
                key=f"lk_c_{comment_id}",
                use_container_width=True
            ):
                cmt['like_count'] = cmt.get('like_count', 0) + 1

                requests.post(
                    f"{API_URL}/like/comment/{comment_id}",
                    headers=headers
                )
                st.rerun()

            # -------------------------
            # 💬 Reply
            # -------------------------
            if cols[2].button(
                "💬",
                key=f"rp_c_{comment_id}",
                use_container_width=True
            ):
                st.session_state[reply_key] = True

            # -------------------------
            # 🔽 Expand / Collapse
            # 只有有子留言才顯示
            # -------------------------
            if has_replies:

                is_expanded = st.session_state[expand_key]
                toggle_text = "收合" if is_expanded else "展開"

                if cols[3].button(
                    toggle_text,
                    key=f"tg_c_{comment_id}",
                    use_container_width=True
                ):
                    st.session_state[expand_key] = not is_expanded
                    st.rerun()

            else:
                # 沒子留言 → 保留版面但不顯示按鈕
                cols[3].empty()

            # =========================
            # 4️⃣ Reply input（inline）
            # =========================
            if st.session_state.get(reply_key, False):
                with st.form(f"form_c_{comment_id}"):

                    reply_text = st.text_input(
                        f"回覆 {cmt['author_name']}..."
                    )

                    if st.form_submit_button("送出"):
                        requests.post(
                            f"{API_URL}/posts/{post_id}/comments",
                            json={
                                "content": reply_text,
                                "parent_id": comment_id
                            },
                            headers=headers
                        )

                        st.session_state[reply_key] = False
                        st.rerun()

        # =========================
        # 5️⃣ recursion（收合才顯示）
        # =========================
        if has_replies and st.session_state[expand_key]:
            render_comments(
                cmt['replies'],
                post_id,
                headers,
                depth + 1
            )


# --- 主畫面：功能測試區 ---
st.divider()

if not st.session_state.access_token:
    st.info("👈 請先從左側登入或註冊以開始測試功能。")
else:
    st.write(f"### 📍 當前身分：**{st.session_state.username}**")
    
    # 測試「我的資訊」API
    headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
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
                resp = requests.post(f"{API_URL}/posts", json={"content": content}, headers=headers)
                if resp.status_code == 200:
                    st.success("發布成功！")
                else:
                    st.error("發布失敗")
            else:
                st.warning("內容不能為空喔！")

    st.divider()

    # --- 貼文牆列表 ---
    st.subheader("🌍 貼文廣場")
    posts_resp = requests.get(f"{API_URL}/posts")
    if posts_resp.status_code == 200:
        all_posts = posts_resp.json()
        if not all_posts:
            st.write("目前還沒有人發文喔～")

        # --- 貼文廣場部分 ---
        for p in reversed(all_posts):
            with st.container(border=True):
                st.markdown(f"**{p['username']}** · <small>{p['created_at'][:16]}</small>", unsafe_allow_html=True)
                st.write(p['content'])
                
                # --- 修正 1：貼文按讚按鈕顯示數量 ---
                # 假設我們在 session_state 存了當前使用者的 id 來判斷是否點過讚 (選配)
                likes_count = p.get('likes_count', 0)
                if st.button(f"👍 {likes_count} 人按讚", key=f"lk_p_{p['id']}"):
                    resp = requests.post(f"{API_URL}/like/post/{p['id']}", headers=headers)
                    st.rerun()

                st.divider()
                st.write("💬 留言區")
                
                # --- 修正 2：顯示留言 ---
                if "comments" in p and p['comments']:
                    render_comments(p['comments'], p['id'], headers)
                else:
                    st.caption("尚無留言")
                    
                # 一級留言輸入
                with st.expander("寫下你的留言..."):
                    with st.form(f"root_cmt_{p['id']}"):
                        new_cmt = st.text_input("留言內容")
                        if st.form_submit_button("留言"):
                            requests.post(f"{API_URL}/posts/{p['id']}/comments", json={"content": new_cmt}, headers=headers)
                            st.rerun()