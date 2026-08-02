# Repository instructions

Follow `AGENTS.md` and the nearest nested `AGENTS.md`. Use `rg` to identify the smallest owning code path and closest test before reading broad files.

The primary application is the authenticated direct web interface in `web_interface.py` and `static/`; `app.py` is a legacy Streamlit surface. Preserve the lifecycle, identity, transcript/title, audit, idempotency, security, and temporary-database invariants documented in `AGENTS.md`.

Make focused changes, add a regression test, run narrow checks first, and run the complete gate before declaring commit readiness. Never claim that local QA is a deployment or production verification. Do not modify the tracked database during tests.
