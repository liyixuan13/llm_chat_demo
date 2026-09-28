# AGENTS.md

Small Streamlit/console demo calling the DeepSeek chat API. Portfolio project 1:
multi-turn chat, role switching (system prompt), temperature/max_tokens, and streaming.

## Environment (non-obvious)
- Windows + PowerShell. The system `python` (3.11.5) does **not** have the deps installed. Use the venv: `venv\Scripts\python.exe` / `venv\Scripts\streamlit.exe`. Only there are `streamlit 1.64.0`, `requests`, `python-dotenv` available.
- `requirements.txt` lists deps for fresh installs; the local `venv/` is gitignored.

## Entrypoints
- `app.py` (repo root) — Streamlit web chat, the main program. Run from repo root: `venv\Scripts\streamlit.exe run app.py`. Must be started with `streamlit run`; plain `python app.py` only emits `missing ScriptRunContext` warnings.
- `main.py` — console multi-turn chat. Run: `venv\Scripts\python.exe main.py`. Loads `.env` via python-dotenv; needs `DEEPSEEK_API_KEY` and `DEEPSEEK_API_URL`.

## Secrets (IMPORTANT)
- Local key sources, in priority order: `st.secrets` → `.streamlit/secrets.toml` → `secrets.toml` at root → `DEEPSEEK_API_KEY` env var.
- `.gitignore` covers `.env`, `.streamlit/secrets.toml`, and `secrets.toml`.
- **Known leak:** the first commit (`0de93b6`) contains a hardcoded real API key in `main.py`. It was removed in the working tree but remains in git history. The key must be revoked/rotated on the DeepSeek side; purge history only with explicit user request (force-push).

## Deploy
- Streamlit Community Cloud (https://share.streamlit.io), repo `liyixuan13/llm_chat_demo`, branch `main`, main file `app.py`. Set `DEEPSEEK_API_KEY` in the app's Secrets. Chosen over HuggingFace Spaces because HF's free tier now only offers Static Spaces (no Python, no Secrets). See README "部署到 Streamlit Community Cloud".
