from __future__ import annotations
from typing import Literal, Optional, TypedDict
from pydantic import BaseModel, Field

class ContextChunk(BaseModel):
    title: str
    text: str

class QAExample(BaseModel):
    qid: str
    difficulty: Literal["easy", "medium", "hard"]
    question: str
    gold_answer: str
    context: list[ContextChunk]

class JudgeResult(BaseModel):
    score: Literal[0, 1] = Field(
        description="1 nếu câu trả lời đúng, 0 nếu sai"
    )
    reason: str = Field(
        description="Giải thích ngắn gọn tại sao đúng hoặc sai"
    )
    missing_evidence: list[str] = Field(
        default_factory=list,
        description="Danh sách bằng chứng còn thiếu (chỉ khi sai)"
    )
    spurious_claims: list[str] = Field(
        default_factory=list,
        description="Danh sách những thông tin sai trong câu trả lời (chỉ khi sai)"
    )

class ReflectionEntry(BaseModel):
    attempt_id: int = Field(
        description="Số thứ tự lần thử (1-indexed)"
    )
    failure_reason: str = Field(
        description="Lý do tại sao lần thử này thất bại"
    )
    lesson: str = Field(
        description="Bài học rút ra từ lỗi này"
    )
    next_strategy: str = Field(
        description="Chiến thuật cụ thể cho lần thử tiếp theo"
    )

class AttemptTrace(BaseModel):
    attempt_id: int
    answer: str
    score: int
    reason: str
    reflection: Optional[ReflectionEntry] = None
    token_estimate: int = 0
    latency_ms: int = 0

class RunRecord(BaseModel):
    qid: str
    question: str
    gold_answer: str
    agent_type: Literal["react", "reflexion"]
    predicted_answer: str
    is_correct: bool
    attempts: int
    token_estimate: int
    latency_ms: int
    failure_mode: Literal["none", "entity_drift", "incomplete_multi_hop", "wrong_final_answer", "looping", "reflection_overfit"]
    reflections: list[ReflectionEntry] = Field(default_factory=list)
    traces: list[AttemptTrace] = Field(default_factory=list)

class ReportPayload(BaseModel):
    meta: dict
    summary: dict
    failure_modes: dict
    examples: list[dict]
    extensions: list[str]
    discussion: str

class ReflexionState(TypedDict):
    question: str
    context: list[str]
    trajectory: list[str]
    reflection_memory: list[str]
    attempt_count: int
    success: bool
    final_answer: str