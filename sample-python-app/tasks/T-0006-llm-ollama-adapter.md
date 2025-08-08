---
id: T-0006
title: LiteLLM + Ollama adapter (disabled by default)
type: feature
priority: P2
depends_on: [T-0003]
status: queued
owner: unassigned
estimate: 4h
acceptance:
  - "Adapter reads OLLAMA_BASE_URL and per-role models from env"
  - "Developer can request a 3–5 line change plan (dry_run gate)"
auto_policy: review_required
---

## Description
Implement an LLM adapter using LiteLLM that can optionally route to an Ollama backend. The adapter should read `OLLAMA_BASE_URL` and per-role model names from environment variables. Include a dry-run capability where the developer can ask for a brief 3–5 line change plan without executing edits.

## Deliverables
- `codex-orchestrator/adapters/llm_litellm.py`
- `codex-orchestrator/prompts/*.md`
- `.env.example` updates