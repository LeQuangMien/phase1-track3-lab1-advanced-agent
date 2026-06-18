"""
llm_runtime.py — Thay thế mock_runtime.py bằng LLM thật qua OpenRouter API.

Cấu hình:
  export OPENROUTER_API_KEY="sk-or-..."
  export REFLEXION_RUNTIME=llm
  export REFLEXION_MODEL="deepseek/deepseek-r1-0528-qwen3-8b:free"   # tuỳ chọn
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import requests

from .prompts import ACTOR_SYSTEM, EVALUATOR_SYSTEM, REFLECTOR_SYSTEM
from .schemas import JudgeResult, QAExample, ReflectionEntry

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Cấu hình
# ─────────────────────────────────────────────

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Đọc từ env, fallback về deepseek-v3-0324 (free, ổn định)
DEFAULT_MODEL = os.environ.get("REFLEXION_MODEL", "deepseek/deepseek-v3-0324")

# Retry settings
MAX_RETRIES = 3
RETRY_BACKOFF = [2, 5, 10]   # giây chờ sau mỗi lần thất bại

# Giới hạn ký tự context gửi lên để tránh vượt context window
MAX_CONTEXT_CHARS = 12_000

# failure_mode fallback khi không có mock data
FAILURE_MODE_BY_QID: dict[str, str] = {}


# ─────────────────────────────────────────────
# Helper nội bộ
# ─────────────────────────────────────────────

def _truncate_context(text: str, max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """Cắt bớt context nếu quá dài, thêm dấu hiệu để model biết."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[... context truncated for length ...]"


def _call_llm(
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 512,
) -> tuple[str, int, int]:
    """
    Gọi OpenRouter API với retry + backoff.

    Trả về: (content, input_tokens, output_tokens)
    Raises RuntimeError nếu hết retry mà vẫn thất bại.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise EnvironmentError(
            "OPENROUTER_API_KEY chưa được set.\n"
            "Chạy: $env:OPENROUTER_API_KEY='sk-or-...'  (PowerShell)\n"
            "hoặc: export OPENROUTER_API_KEY='sk-or-...'  (bash)"
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/VinUni-AI20k/phase1-track3-lab1-advanced-agent",
        "X-Title": "Reflexion Agent Lab",
    }

    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    }

    last_error: str = "unknown"

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=60,
            )
        except requests.exceptions.Timeout:
            last_error = "request timeout"
            logger.warning("[LLM] Timeout on attempt %d/%d", attempt + 1, MAX_RETRIES)
            _sleep_backoff(attempt)
            continue
        except requests.exceptions.RequestException as exc:
            last_error = str(exc)
            logger.warning("[LLM] Network error attempt %d/%d: %s", attempt + 1, MAX_RETRIES, exc)
            _sleep_backoff(attempt)
            continue

        # HTTP-level error (4xx/5xx)
        if resp.status_code != 200:
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            logger.warning("[LLM] API error attempt %d/%d: %s", attempt + 1, MAX_RETRIES, last_error)
            # 429 rate-limit: chờ lâu hơn
            if resp.status_code == 429:
                time.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)] * 2)
            else:
                _sleep_backoff(attempt)
            continue

        data = resp.json()

        # Kiểm tra có choices không
        choices = data.get("choices") or []
        if not choices:
            last_error = f"empty choices: {json.dumps(data)[:200]}"
            logger.warning("[LLM] No choices attempt %d/%d: %s", attempt + 1, MAX_RETRIES, last_error)
            _sleep_backoff(attempt)
            continue

        # Kiểm tra content không None
        content = (choices[0].get("message") or {}).get("content")
        if content is None:
            # Log toàn bộ response để dễ debug
            finish_reason = choices[0].get("finish_reason", "unknown")
            last_error = f"content=None, finish_reason={finish_reason}, data={json.dumps(data)[:300]}"
            logger.warning("[LLM] Null content attempt %d/%d: %s", attempt + 1, MAX_RETRIES, last_error)
            _sleep_backoff(attempt)
            continue

        # Thành công
        usage = data.get("usage") or {}
        input_tokens: int  = usage.get("prompt_tokens", 0)
        output_tokens: int = usage.get("completion_tokens", 0)
        return content.strip(), input_tokens, output_tokens

    # Hết retry
    raise RuntimeError(
        f"OpenRouter thất bại sau {MAX_RETRIES} lần thử. "
        f"Model: {model}. Lỗi cuối: {last_error}"
    )


def _sleep_backoff(attempt: int) -> None:
    delay = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
    logger.info("[LLM] Retry in %ds...", delay)
    time.sleep(delay)


def _parse_json_safe(text: str) -> dict[str, Any]:
    """
    Parse JSON từ LLM response.
    Xử lý: JSON thuần, ```json...```, ``` ... ```, text thừa xung quanh.
    """
    text = text.strip()

    # Cách 1: tìm { đầu và } cuối — extract JSON object bên trong
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    # Cách 2: parse toàn bộ text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Cách 3: bỏ markdown fence thủ công
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return json.loads("\n".join(lines).strip())


# ─────────────────────────────────────────────
# Hàm 1: Actor
# ─────────────────────────────────────────────

def actor_answer(
    example: QAExample,
    attempt_id: int,
    agent_type: str,
    reflection_memory: list[str],
) -> tuple[str, int, int]:
    """Trả lời câu hỏi. Trả về (answer, input_tokens, output_tokens)."""

    context_text = "\n\n".join(
        f"[{i+1}] {chunk.title}\n{chunk.text}"
        for i, chunk in enumerate(example.context)
    )
    context_text = _truncate_context(context_text)

    reflection_section = ""
    if reflection_memory:
        reflection_section = (
            "\n\n## Previous attempt reflections (MUST follow the strategy below):\n"
            + "\n".join(f"- {m}" for m in reflection_memory)
        )

    user_prompt = (
        f"Question: {example.question}\n\n"
        f"Context passages:\n{context_text}"
        f"{reflection_section}"
    )

    content, in_tok, out_tok = _call_llm(
        system=ACTOR_SYSTEM,
        user=user_prompt,
        temperature=0.0,
        max_tokens=128,
    )

    answer = content
    for prefix in ("answer:", "the answer is", "final answer:"):
        if answer.lower().startswith(prefix):
            answer = answer[len(prefix):].strip()
            break

    logger.debug("[Actor] qid=%s attempt=%d → %r  tok=%d+%d",
                 example.qid, attempt_id, answer, in_tok, out_tok)
    return answer, in_tok, out_tok


# ─────────────────────────────────────────────
# Hàm 2: Evaluator
# ─────────────────────────────────────────────

def evaluator(
    example: QAExample,
    answer: str,
    input_tokens_actor: int = 0,
    output_tokens_actor: int = 0,
) -> tuple[JudgeResult, int, int]:
    """Chấm điểm câu trả lời. Trả về (JudgeResult, input_tokens, output_tokens)."""

    user_prompt = (
        f"Question: {example.question}\n"
        f"Gold answer: {example.gold_answer}\n"
        f"Predicted answer: {answer}"
    )

    content, in_tok, out_tok = _call_llm(
        system=EVALUATOR_SYSTEM,
        user=user_prompt,
        temperature=0.0,
        max_tokens=256,
    )

    try:
        parsed = _parse_json_safe(content)
        judge = JudgeResult(
            score=int(parsed.get("score", 0)),
            reason=str(parsed.get("reason", "No reason provided.")),
            missing_evidence=parsed.get("missing_evidence", []),
            spurious_claims=parsed.get("spurious_claims", []),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning("[Evaluator] Parse error: %s — raw: %r", exc, content[:200])
        from .utils import normalize_answer
        is_correct = normalize_answer(example.gold_answer) == normalize_answer(answer)
        judge = JudgeResult(
            score=1 if is_correct else 0,
            reason=f"Fallback string match (parse error: {exc})",
        )

    logger.debug("[Evaluator] qid=%s score=%d tok=%d+%d",
                 example.qid, judge.score, in_tok, out_tok)
    return judge, in_tok, out_tok


# ─────────────────────────────────────────────
# Hàm 3: Reflector
# ─────────────────────────────────────────────

def reflector(
    example: QAExample,
    attempt_id: int,
    judge: JudgeResult,
) -> tuple[ReflectionEntry, int, int]:
    """Phân tích lỗi và đề xuất chiến lược. Trả về (ReflectionEntry, input_tokens, output_tokens)."""

    missing_str  = "\n".join(f"  - {e}" for e in judge.missing_evidence)  or "  (none)"
    spurious_str = "\n".join(f"  - {c}" for c in judge.spurious_claims)   or "  (none)"
    wrong_answer = judge.spurious_claims[0] if judge.spurious_claims else "(unknown)"

    user_prompt = (
        f"Question: {example.question}\n"
        f"Wrong answer given: {wrong_answer}\n"
        f"Evaluator reason: {judge.reason}\n"
        f"Missing evidence:\n{missing_str}\n"
        f"Spurious claims:\n{spurious_str}"
    )

    content, in_tok, out_tok = _call_llm(
        system=REFLECTOR_SYSTEM,
        user=user_prompt,
        temperature=0.0,
        max_tokens=256,
    )

    try:
        parsed = _parse_json_safe(content)
        entry = ReflectionEntry(
            attempt_id=attempt_id,
            failure_reason=str(parsed.get("failure_reason", judge.reason)),
            lesson=str(parsed.get("lesson", "Need to reason more carefully.")),
            next_strategy=str(parsed.get("next_strategy", "Re-read all context passages.")),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning("[Reflector] Parse error: %s — raw: %r", exc, content[:200])
        entry = ReflectionEntry(
            attempt_id=attempt_id,
            failure_reason=judge.reason,
            lesson="Need to complete all reasoning hops before answering.",
            next_strategy="Re-read all context passages and verify the final entity.",
        )

    logger.debug("[Reflector] qid=%s attempt=%d strategy=%r tok=%d+%d",
                 example.qid, attempt_id, entry.next_strategy[:60], in_tok, out_tok)
    return entry, in_tok, out_tok