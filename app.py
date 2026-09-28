import json
import os
from pathlib import Path

try:
    import tomllib  # Python 3.11+ 标准库
except ModuleNotFoundError:  # 兼容 3.10 及更低版本
    tomllib = None

import requests
import streamlit as st

st.set_page_config(
    page_title="AI 聊天助手",
    page_icon=":material/chat:",
    layout="centered",
)

# ========= 配置 =========
MAX_CHARS = 500          # 单次提问的最大字数
REQUEST_TIMEOUT = 30     # 非流式请求超时时间（秒）
STREAM_TIMEOUT = (10, 60)  # 流式：(建立连接超时, 两次数据之间的读取超时)
API_URL = "https://api.deepseek.com/v1/chat/completions"

# 上下文管理：每次最多携带最近 N 条历史消息（不含 system）。
# 上下文窗口和 token 都是有限的，历史越长越贵、越慢，所以要做简单截断。
MAX_HISTORY_MESSAGES = 10

# ========= 角色与 Prompt 配置 =========
# role 消息结构：system 决定 AI 的身份/风格，user 是用户提问，assistant 是 AI 的历史回答
ROLES: dict[str, str] = {
    "通用助手": "你是一个乐于助人的中文 AI 助手，回答简洁准确。",
    "代码助手": (
        "你是一名资深 Python 工程师。回答技术问题时，先给出可运行的示例代码，"
        "再逐行解释关键点；如果需求不明确，先提问澄清，不要编造不存在的 API。"
    ),
    "学习助手": (
        "你是一位耐心的编程导师，面向零基础学习者。用通俗的比喻讲解概念，"
        "先给结论再分步骤展开，避免堆砌术语；必要时举一个生活化的例子。"
    ),
}
DEFAULT_ROLE = "通用助手"


# ========= 密钥读取 =========
@st.cache_resource
def get_api_key() -> str | None:
    """按优先级读取密钥：st.secrets > .streamlit/secrets.toml > 根目录 secrets.toml > 环境变量。

    本地开发放 .streamlit/secrets.toml；线上（如 HuggingFace Spaces）用平台的 Secrets，
    这样代码里永远不出现明文密钥。
    """
    try:
        return st.secrets["DEEPSEEK_API_KEY"]
    except Exception:
        pass

    for secrets_path in (
        Path(__file__).resolve().parent / ".streamlit" / "secrets.toml",
        Path(__file__).resolve().parent / "secrets.toml",
    ):
        if secrets_path.exists() and tomllib is not None:
            try:
                with secrets_path.open("rb") as f:
                    key = tomllib.load(f).get("DEEPSEEK_API_KEY")
            except Exception:
                key = None
            if key:
                return key

    return os.getenv("DEEPSEEK_API_KEY")


# ========= 上下文构造（多轮对话的关键） =========
def build_request_messages(
    system_prompt: str,
    history: list[dict[str, str]],
) -> list[dict[str, str]]:
    """把「角色设定 + 最近的历史消息」拼成本次请求的 messages。

    每次请求都要把历史重新带上，模型本身不记得上一轮——它看到的只有这一份列表。
    历史太长时简单截断：只保留最近 MAX_HISTORY_MESSAGES 条，丢弃更早的。
    """
    recent_history = history[-MAX_HISTORY_MESSAGES:]
    return [{"role": "system", "content": system_prompt}, *recent_history]


# ========= 调用 LLM（非流式） =========
def call_llm(
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> str:
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {get_api_key()}",
            "Content-Type": "application/json",
        },
        json={
            "model": "deepseek-chat",
            # 关键：这里传的是完整的消息列表（system + 历史 + 最新提问）
            "messages": messages,
            # temperature 越低越稳定保守，越高越有创造性（0~2）
            "temperature": temperature,
            # max_tokens 限制单次回答的最大长度
            "max_tokens": max_tokens,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ========= 调用 LLM（流式，打字机效果） =========
def stream_llm(
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
):
    """逐块产出 AI 文本的生成器。

    与普通请求的区别：
    - 请求体加 "stream": True，告诉服务端「分段返回」
    - requests.post(..., stream=True)，不会一次性把响应读完
    - 用 iter_lines() 逐行读取 SSE（Server-Sent Events）数据，格式为 `data: {...}`
    - 最后会收到一行 `data: [DONE]` 表示结束
    """
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {get_api_key()}",
            "Content-Type": "application/json",
        },
        json={
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        },
        timeout=STREAM_TIMEOUT,
        stream=True,
    )
    resp.raise_for_status()  # 连接层/HTTP 错误在这里抛出（生成器首次迭代时执行）

    for raw_line in resp.iter_lines():
        if not raw_line:
            continue
        # 手动按 utf-8 解码，避免中文乱码（iter_lines 默认可能用 latin-1）
        line = raw_line.decode("utf-8")
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            break
        # SSE 里的增量内容在 choices[0].delta.content，可能为 None（如首个事件只有 role）
        delta = json.loads(payload)["choices"][0]["delta"].get("content")
        if delta:
            yield delta


# 把 requests / 解析异常翻译成给用户看的中文提示
def friendly_error(exc: Exception) -> str:
    if isinstance(exc, requests.exceptions.Timeout):
        return "请求超时：网络较慢或服务无响应，请稍后重试。"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "网络连接失败：请检查网络后重试。"
    if isinstance(exc, requests.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        if status == 401:
            return "API 密钥无效或未授权，请检查 DEEPSEEK_API_KEY。"
        if status == 429:
            return "请求过于频繁（限流），请稍后再试。"
        return f"接口返回错误：HTTP {status}。"
    if isinstance(exc, (KeyError, IndexError, ValueError)):
        return "响应解析失败：AI 返回的数据格式异常。"
    if isinstance(exc, requests.exceptions.RequestException):
        return f"请求出错：{exc}"
    return f"未知错误：{exc}"


# 流式路径可能抛出的异常类型，统一在页面上捕获
STREAM_ERRORS = (
    requests.exceptions.RequestException,
    KeyError,
    IndexError,
    ValueError,
)


def ask_llm(
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> tuple[bool, str]:
    """非流式路径：统一处理异常，返回 (是否成功, 文本)。"""
    if not get_api_key():
        return False, "未检测到 API Key，请检查 .streamlit/secrets.toml 或环境变量配置。"

    try:
        return True, call_llm(messages, temperature, max_tokens)
    except STREAM_ERRORS as e:
        return False, friendly_error(e)


# ========= 页面 =========
st.title("AI 聊天助手", icon=":material/chat:")
st.caption("Python + Streamlit + DeepSeek · 多轮对话 / 角色切换 / 流式输出")

# 对话历史：只存 user / assistant 两种角色，跨页面重跑保留在 session_state 里
st.session_state.setdefault("messages", [])
history: list[dict[str, str]] = st.session_state.messages

# ========= 侧边栏：角色与参数 =========
with st.sidebar:
    st.subheader("角色与参数")

    role = st.segmented_control(
        "AI 角色",
        options=list(ROLES.keys()),
        default=DEFAULT_ROLE,
        key="role",
    )
    # 用户取消选择时会返回 None，这里回退到默认角色
    role = role or DEFAULT_ROLE

    temperature = st.slider(
        "temperature（随机性）",
        min_value=0.0,
        max_value=2.0,
        value=0.7,
        step=0.1,
        help="越低回答越稳定保守，越高越有创造性；写代码建议 0.2~0.5。",
    )
    max_tokens = st.slider(
        "max_tokens（回答最大长度）",
        min_value=256,
        max_value=4096,
        value=1024,
        step=128,
        help="限制单次回答的长度上限，越大越可能被截断前用完词数。",
    )

    stream_output = st.toggle(
        "流式输出（打字机效果）",
        value=True,
        help="开启后边生成边显示；关闭则等全部生成完一次性显示，可用来对比。",
    )

    st.divider()

    # 上下文用量提示：历史条数 / 本轮实际发送的字符数（粗略估计 token 消耗）
    sent_messages = build_request_messages(ROLES[role], history)
    sent_chars = sum(len(m["content"]) for m in sent_messages)
    st.caption(
        f"历史 {len(history)} 条 · 本次发送 {len(sent_messages)} 条"
        f"（含 system，上限 {MAX_HISTORY_MESSAGES + 1} 条）· 约 {sent_chars} 字"
    )

    with st.expander("查看本次请求的 messages"):
        st.json(sent_messages)

    if st.button("清空对话", icon=":material/delete:"):
        st.session_state.messages = []
        st.rerun()


# ========= 渲染历史对话 =========
for message in history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ========= 处理新输入 =========
if prompt := st.chat_input("输入你的问题...", max_chars=MAX_CHARS):
    # 1) 先把用户提问加入历史并显示
    history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2) 用「角色设定 + 完整历史」构造请求（这就是多轮记忆的关键）
    request_messages = build_request_messages(
        ROLES.get(role, ROLES[DEFAULT_ROLE]), history
    )

    # 3) 调用大模型并显示回答
    with st.chat_message("assistant"):
        if not get_api_key():
            st.error(
                "未检测到 API Key，请检查 .streamlit/secrets.toml 或环境变量配置。",
                icon=":material/error:",
            )
            history.pop()
        elif stream_output:
            # 流式：st.write_stream 会边接收生成器产出的块边渲染，并返回完整文本
            try:
                answer = st.write_stream(
                    stream_llm(request_messages, temperature, max_tokens)
                )
                # 成功才把回答写入历史
                history.append({"role": "assistant", "content": answer})
            except STREAM_ERRORS as e:
                # 流式过程中断（网络/限流/解析失败）也能给出友好提示
                st.error(friendly_error(e), icon=":material/error:")
                # 回滚这条提问，避免留下没有回答的悬空消息
                history.pop()
        else:
            with st.spinner("AI 思考中..."):
                ok, text = ask_llm(request_messages, temperature, max_tokens)
            if ok:
                st.markdown(text)
                history.append({"role": "assistant", "content": text})
            else:
                st.error(text, icon=":material/error:")
                history.pop()
