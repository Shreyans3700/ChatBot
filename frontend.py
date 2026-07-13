import json
import uuid

import requests
import streamlit as st

# -----------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------
st.set_page_config(page_title="ChatBot", layout="wide")


# Prefer st.secrets (put these in .streamlit/secrets.toml) but allow
# manual override from the sidebar so this is easy to demo without setup.
# st.secrets raises if no secrets.toml exists at all (rather than just
# behaving like a normal dict), so wrap access defensively.
def get_secret(key: str, default: str = "") -> str:
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


DEFAULT_BACKEND_URL = get_secret("BACKEND_URL", "http://localhost:8000")
DEFAULT_API_KEY = get_secret("API_KEY", "")

with st.sidebar:
    st.markdown("### Connection")
    backend_url = st.text_input("Backend URL", value=DEFAULT_BACKEND_URL).rstrip("/")
    api_key = st.text_input("API Key", value=DEFAULT_API_KEY, type="password")
    st.divider()

HEADERS = {"X-API-Key": api_key, "Content-Type": "application/json"}


# -----------------------------------------------------------------------
# Backend calls
# -----------------------------------------------------------------------
def fetch_sessions() -> list[dict]:
    try:
        # Matches the backend's actual route name: /getSessionMetaData.
        resp = requests.get(f"{backend_url}/getSessionMetaData", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # Endpoint currently returns a bare list, not {"sessions": [...]}.
        return data if isinstance(data, list) else data.get("sessions", [])
    except requests.RequestException as e:
        st.sidebar.error(f"Could not load sessions: {e}")
        return []


def load_session_history(session_id: str) -> list[dict]:
    try:
        # NOTE: matches the current backend, which reads session_id from the
        # JSON body even on a GET request. If you apply the Query(...) fix
        # from the code review, switch `json=` to `params=` below.
        resp = requests.get(
            f"{backend_url}/getSessionHistory",
            headers=HEADERS,
            json={"session_id": session_id},
            timeout=10,
        )
        resp.raise_for_status()
        history = resp.json().get("history", [])
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
    """Generator that yields answer tokens as they arrive, and stashes the
    final metadata (model/tokens/latency) in session_state when the
    'done' event arrives."""
    payload = {"session_id": session_id, "user_query": user_query}
    try:
        with requests.post(
            f"{backend_url}/chat/stream",
            headers=HEADERS,
            json=payload,
            stream=True,
            timeout=120,
        ) as resp:
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
# Session state
# -----------------------------------------------------------------------
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []


def start_new_chat():
    st.session_state.current_session_id = str(uuid.uuid4())
    st.session_state.messages = []


def switch_session(session_id: str):
    st.session_state.current_session_id = session_id
    st.session_state.messages = load_session_history(session_id)


# -----------------------------------------------------------------------
# Sidebar: session list
# -----------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Sessions")

    if st.button("+ New chat", use_container_width=True):
        start_new_chat()
        st.rerun()

    st.caption("Click a session to load its history.")

    sessions = fetch_sessions()
    if not sessions:
        st.caption("No saved sessions yet — send a message to create one.")
    for s in sessions:
        session_id = s["session_id"]
        # Sessions now carry a real title (see title-generation feature);
        # fall back to the short session id if it's ever missing/empty.
        title = (s.get("title") or "").strip() or session_id[:8]
        is_current = session_id == st.session_state.current_session_id
        button_label = f"{'➤ ' if is_current else ''}{title}"
        if st.button(button_label, key=f"session_{session_id}", use_container_width=True):
            switch_session(session_id)
            st.rerun()

    st.divider()
    st.caption(f"Current session: `{st.session_state.current_session_id[:8]}`")


# -----------------------------------------------------------------------
# Main chat area
# -----------------------------------------------------------------------
st.title("ChatBot")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Type your message..."):
    if not api_key:
        st.error("Enter your API key in the sidebar first.")
    else:
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
                f"model: {meta.get('model', 'unknown')} · "
                f"tokens: {meta.get('tokens', 'n/a')} · "
                f"latency: {latency_str}"
            )