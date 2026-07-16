"""测试 deepseek-chat JSON 输出的可靠性"""
import sys, os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ != "__main__" and os.getenv("RUN_LIVE_LLM_TESTS") != "1":
    pytest.skip("manual live LLM script; set RUN_LIVE_LLM_TESTS=1 to collect", allow_module_level=True)

import json
from llm_factory import create_llm

llm = create_llm(temperature=0.0)

prompt = """You are a PM. Create a PRD for an e-commerce homepage.

Output ONLY valid JSON with these EXACT fields:
{
  "page_name": "string",
  "page_type": "e-commerce",
  "features": [
    {"name": "string", "description": "string", "priority": "high"}
  ]
}

Output ONLY the JSON object, no markdown code blocks, no explanation."""

response = llm.invoke(prompt)
content = response.content.strip()
# Strip markdown code blocks if present
if content.startswith("```"):
    content = content.split("```")[1]
    if content.startswith("json"):
        content = content[4:]
    content = content.strip()

print(f"Raw output (first 300 chars): {content[:300]}")
obj = json.loads(content)
print(f"Parsed: page_name={obj.get('page_name')}, features={len(obj.get('features', []))}")
print("OK")
