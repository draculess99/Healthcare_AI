# Groq LLM-like Committee Response Patch

This patch keeps the Freeze Fix v4 safety design but makes **Groq mode** feel more like a real LLM response.

## What changed

- Local mode still uses the fast, no-backend, no-token Streamlit committee.
- When the sidebar is set to **Remote LLM Mode** and provider is **Groq**, the app now:
  1. Calculates the forecast/usable-stock/risk facts locally first.
  2. Sends those facts to Groq in one short non-streaming call.
  3. Uses Groq only to rewrite the committee response into a more natural control-tower narrative.
  4. Falls back to the local response if Groq errors or times out.

## Important

Groq does **not** change the numeric calculation. It only improves the wording of:

- Demand Forecast Agent
- Inventory Risk Agent
- Packing Priority Agent
- Clinical Safety Agent
- Final Recommendation Agent
- Committee Consensus Summary

## Expected mode label

When Groq works, the committee output should show:

```text
actual_agent_mode: remote_groq_llm_like_frontend_safe
```

When Groq fails, it falls back to:

```text
actual_agent_mode: streamlit_v4_local_fallback_after_groq_error
```

## Files changed

- `frontend/dashboard.py`
