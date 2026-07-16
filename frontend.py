import json
import uuid

import requests
import streamlit as st

# -----------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------
st.set_page_config(page_title="ChatBot", layout="wide")


def get_secret(key: str, default: str = "") -> str:
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


DEFAULT_BACKEND_URL = get_secret("BACKEND_URL", "http://localhost:8000")

with st.sidebar:
    st.markdown("### Connection")
    backend_url = st.text_input("Backend URL", value=DEFAULT_BACKEND_URL).rstrip("/")
    st.divider()


# -----------------------------------------------------------------------
# Session state
# -----------------------------------------------------------------------
if "auth_token" not in st.session_state:
    st.session_state.auth_token = ""
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []


def is_authenticated() -> bool:
    return bool(st.session_state.auth_token)


def logout_user() -> None:
    st.session_state.auth_token = ""
    st.session_state.auth_user = None
    st.session_state.current_session_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.pop("_last_meta", None)


def start_new_chat() -> None:
    st.session_state.current_session_id = str(uuid.uuid4())
    st.session_state.messages = []


def switch_session(session_id: str) -> None:
    st.session_state.current_session_id = session_id
    st.session_state.messages = load_session_history(session_id)


def auth_headers() -> dict[str, str]:
    if not is_authenticated():
        return {}
    return {
        "Authorization": f"Bearer {st.session_state.auth_token}",
        "Content-Type": "application/json",
    }


def public_headers() -> dict[str, str]:
    return {"Content-Type": "application/json"}


def _request_json(
    method: str,
    path: str,
    *,
    json_payload=None,
    auth: bool = False,
    stream: bool = False,
):
    url = f"{backend_url}{path}"
    headers = auth_headers() if auth else public_headers()
    response = requests.request(
        method,
        url,
        headers=headers,
        json=json_payload,
        stream=stream,
        timeout=120 if stream else 10,
    )
    if response.status_code == 401 and auth:
        logout_user()
        raise requests.HTTPError("Session expired. Please sign in again.")
    response.raise_for_status()
    return response


# -----------------------------------------------------------------------
# Auth helpers
# -----------------------------------------------------------------------
def _extract_error_detail(response: requests.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict):
            detail = data.get("detail")
            if isinstance(detail, str) and detail:
                return detail
    except Exception:
        pass
    text = response.text.strip()
    return text or f"HTTP {response.status_code}"


def login_user(email: str, password: str) -> None:
    response = requests.post(
        f"{backend_url}/auth/login",
        headers=public_headers(),
        json={"email": email, "password": password},
        timeout=10,
    )
    if response.status_code >= 400:
        raise RuntimeError(_extract_error_detail(response))
    data = response.json()
    st.session_state.auth_token = data["access_token"]
    st.session_state.auth_user = data["user"]
    start_new_chat()



def signup_user(email: str, password: str) -> None:
    response = requests.post(
        f"{backend_url}/auth/signup",
        headers=public_headers(),
        json={"email": email, "password": password},
        timeout=10,
    )
    if response.status_code >= 400:
        detail = _extract_error_detail(response)
        if response.status_code == 409 or "already registered" in detail.lower():
            raise ValueError("User already exists")
        raise RuntimeError(detail)
    data = response.json()
    st.session_state.auth_token = data["access_token"]
    st.session_state.auth_user = data["user"]
    start_new_chat()


# -----------------------------------------------------------------------
# Backend calls
# -----------------------------------------------------------------------
def fetch_sessions() -> list[dict]:
    if not is_authenticated():
        return []
    try:
        response = _request_json("GET", "/getSessionMetaData", auth=True)
        data = response.json()
        return data if isinstance(data, list) else data.get("sessions", [])
    except requests.RequestException as e:
        st.sidebar.error(f"Could not load sessions: {e}")
        return []


def load_session_history(session_id: str) -> list[dict]:
    if not is_authenticated():
        return []
    try:
        response = requests.get(
            f"{backend_url}/getSessionHistory",
            headers=auth_headers(),
            params={"session_id": session_id},
            timeout=10,
        )
        if response.status_code == 401:
            logout_user()
            st.sidebar.error("Session expired. Please sign in again.")
            return []
        response.raise_for_status()
        history = response.json().get("history", [])
        return [
            {
                "role": "user" if item["role"] == "Human" else "assistant",
                "content": item["content"],
            }
            for item in history
        ]
    except requests.RequestException as e:
        st.sidebar.error(f"Could not load history: {e}")
        return []


def stream_chat_response(session_id: str, user_query: str):
    if not is_authenticated():
        yield "Please sign in to continue."
        return

    payload = {"session_id": session_id, "user_query": user_query}
    try:
        with requests.post(
            f"{backend_url}/chat/stream",
            headers=auth_headers(),
            json=payload,
            stream=True,
            timeout=120,
        ) as resp:
            if resp.status_code == 401:
                logout_user()
                yield "\n\n*(session expired, please sign in again)*"
                return
            resp.raise_for_status()
            event_name = None
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                if raw_line.startswith("event:"):
                    event_name = raw_line.split("event:", 1)[1].strip()
                elif raw_line.startswith("data:"):
                    data_str = raw_line.split("data:", 1)[1].strip()
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if event_name == "token":
                        yield data.get("token", "")
                    elif event_name == "done":
                        st.session_state["_last_meta"] = data
    except requests.RequestException as e:
        st.session_state["_last_meta"] = None
        yield f"\n\n*(error contacting backend: {e})*"


# -----------------------------------------------------------------------
# Sidebar: auth and sessions
# -----------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Account")

    if is_authenticated():
        user = st.session_state.auth_user or {}
        st.success(f"Signed in as {user.get('email', 'unknown')}")
        if st.button("Log out", use_container_width=True):
            logout_user()
            st.rerun()
    else:
        st.caption("Create an account or log in to start.")
        login_tab, signup_tab = st.tabs(["Login", "Sign up"])

        with login_tab:
            with st.form("login_form", clear_on_submit=True):
                login_email = st.text_input("Email", key="login_email")
                login_password = st.text_input(
                    "Password", key="login_password", type="password"
                )
                login_submit = st.form_submit_button("Login", use_container_width=True)
            if login_submit:
                try:
                    login_user(login_email, login_password)
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(f"Login failed: {exc}")
                except RuntimeError as exc:
                    st.error(f"Login failed: {exc}")

        with signup_tab:
            with st.form("signup_form", clear_on_submit=True):
                signup_email = st.text_input("Email", key="signup_email")
                signup_password = st.text_input(
                    "Password", key="signup_password", type="password"
                )
                signup_submit = st.form_submit_button("Create account", use_container_width=True)
            if signup_submit:
                try:
                    signup_user(signup_email, signup_password)
                    st.rerun()
                except ValueError:
                    st.warning("User already exists. Please log in instead.")
                except RuntimeError as exc:
                    st.error(f"Sign up failed: {exc}")
                except requests.RequestException as exc:
                    st.error(f"Sign up failed: {exc}")

    st.divider()
    st.markdown("### Sessions")

    if st.button("+ New chat", use_container_width=True, disabled=not is_authenticated()):
        start_new_chat()
        st.rerun()

    st.caption("Click a session to load its history.")

    if not is_authenticated():
        st.caption("Log in or sign up to view your sessions.")
    else:
        sessions = fetch_sessions()
        if not sessions:
            st.caption("No saved sessions yet - send a message to create one.")
        for s in sessions:
            session_id = s["session_id"]
            title = (s.get("title") or "").strip() or session_id[:8]
            is_current = session_id == st.session_state.current_session_id
            button_label = f"{'> ' if is_current else ''}{title}"
            if st.button(button_label, key=f"session_{session_id}", use_container_width=True):
                switch_session(session_id)
                st.rerun()

    st.divider()
    st.caption(f"Current session: `{st.session_state.current_session_id[:8]}`")


# -----------------------------------------------------------------------
# Main chat area
# -----------------------------------------------------------------------
st.title("ChatBot")

if not is_authenticated():
    st.info("Log in or sign up to start.")
    st.stop()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Type your message..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        answer = st.write_stream(
            stream_chat_response(st.session_state.current_session_id, prompt)
        )

    st.session_state.messages.append({"role": "assistant", "content": answer})

    meta = st.session_state.pop("_last_meta", None)
    if meta:
        latency = meta.get("latency")
        latency_str = f"{latency:.2f}s" if isinstance(latency, (int, float)) else "n/a"
        st.caption(
            f"model: {meta.get('model', 'unknown')} | "
            f"tokens: {meta.get('tokens', 'n/a')} | "
            f"latency: {latency_str}"
        )
