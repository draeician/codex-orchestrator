from litellm import completion

def plan_changes(prompt: str, model: str = "ollama/llama3") -> str:
    try:
        resp = completion(model=model, messages=[{"role":"user","content":prompt}], temperature=0.2, max_tokens=512)
        return resp["choices"][0]["message"]["content"]
    except Exception:
        return "fallback-plan"

