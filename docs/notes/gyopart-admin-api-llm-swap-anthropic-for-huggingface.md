---
title: Gyopart admin_api LLM: swap Anthropic for HuggingFace
date: 2026-05-31
tags: admin-api, llm, huggingface
---

llm_suggester.py uses anthropic SDK — no API key available. Swap for HuggingFace: either huggingface_hub.InferenceClient (cloud, free tier) or Ollama on cluster (Llama 3.1 8B / Mistral 7B, air-gapped). Existing prompt expects JSON output and builds context from both DBs before the LLM call — no tool-calling needed. Decision between HF Inference API vs Ollama deferred to implementation time. The rest of admin_api (discrepancy UI, rules, templates) has no LLM dependency and deploys as-is.
