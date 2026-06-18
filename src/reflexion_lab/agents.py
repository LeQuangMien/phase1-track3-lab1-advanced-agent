from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Literal
from .schemas import AttemptTrace, QAExample, ReflectionEntry, RunRecord

# ─────────────────────────────────────────────────────────────────
# Chọn runtime: "llm" (LLM thật) hoặc "mock" (giả lập, mặc định)
#
# Cách đổi sang LLM thật:
#   import os; os.environ["REFLEXION_RUNTIME"] = "llm"
# Hoặc export REFLEXION_RUNTIME=llm trước khi chạy
# ─────────────────────────────────────────────────────────────────
import os as _os
_RUNTIME = _os.environ.get("REFLEXION_RUNTIME", "mock").lower()

if _RUNTIME == "llm":
    from .llm_runtime import FAILURE_MODE_BY_QID, actor_answer, evaluator, reflector
    _USE_LLM = True
else:
    from .mock_runtime import FAILURE_MODE_BY_QID, actor_answer, evaluator, reflector  # type: ignore
    _USE_LLM = False


@dataclass
class BaseAgent:
    agent_type: Literal["react", "reflexion"]
    max_attempts: int = 1

    def run(self, example: QAExample) -> RunRecord:
        reflection_memory: list[str] = []
        reflections: list[ReflectionEntry] = []
        traces: list[AttemptTrace] = []
        final_answer = ""
        final_score = 0

        for attempt_id in range(1, self.max_attempts + 1):
            t0 = time.monotonic()

            if _USE_LLM:
                # ── LLM thật: lấy token và latency từ response ──
                answer, in_tok_actor, out_tok_actor = actor_answer(
                    example, attempt_id, self.agent_type, reflection_memory
                )
                judge, in_tok_eval, out_tok_eval = evaluator(example, answer)
                latency_ms = int((time.monotonic() - t0) * 1000)
                token_estimate = in_tok_actor + out_tok_actor + in_tok_eval + out_tok_eval
            else:
                # ── Mock: giá trị ước lượng cố định ──
                answer = actor_answer(example, attempt_id, self.agent_type, reflection_memory)
                judge = evaluator(example, answer)
                token_estimate = 320 + (attempt_id * 65) + (120 if self.agent_type == "reflexion" else 0)
                latency_ms = 160 + (attempt_id * 40) + (90 if self.agent_type == "reflexion" else 0)

            trace = AttemptTrace(
                attempt_id=attempt_id,
                answer=answer,
                score=judge.score,
                reason=judge.reason,
                token_estimate=token_estimate,
                latency_ms=latency_ms,
            )
            final_answer = answer
            final_score = judge.score

            if judge.score == 1:
                traces.append(trace)
                break

            # ── Reflexion loop ──────────────────────────────────
            if self.agent_type == "reflexion" and attempt_id < self.max_attempts:
                if _USE_LLM:
                    reflection, in_tok_ref, out_tok_ref = reflector(example, attempt_id, judge)
                    # Cộng thêm token của reflector vào trace
                    trace.token_estimate += in_tok_ref + out_tok_ref
                else:
                    reflection = reflector(example, attempt_id, judge)

                reflections.append(reflection)
                trace.reflection = reflection

                memory_entry = (
                    f"[Attempt {reflection.attempt_id}] "
                    f"Failure: {reflection.failure_reason} | "
                    f"Lesson: {reflection.lesson} | "
                    f"Next strategy: {reflection.next_strategy}"
                )
                reflection_memory.append(memory_entry)

            traces.append(trace)

        total_tokens = sum(t.token_estimate for t in traces)
        total_latency = sum(t.latency_ms for t in traces)
        failure_mode = (
            "none"
            if final_score == 1
            else FAILURE_MODE_BY_QID.get(example.qid, "wrong_final_answer")
        )

        return RunRecord(
            qid=example.qid,
            question=example.question,
            gold_answer=example.gold_answer,
            agent_type=self.agent_type,
            predicted_answer=final_answer,
            is_correct=bool(final_score),
            attempts=len(traces),
            token_estimate=total_tokens,
            latency_ms=total_latency,
            failure_mode=failure_mode,
            reflections=reflections,
            traces=traces,
        )


class ReActAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_type="react", max_attempts=1)


class ReflexionAgent(BaseAgent):
    def __init__(self, max_attempts: int = 3) -> None:
        super().__init__(agent_type="reflexion", max_attempts=max_attempts)