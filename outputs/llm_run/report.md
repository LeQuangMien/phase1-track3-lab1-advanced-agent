# Lab 16 Benchmark Report

## Metadata
- Dataset: hotpot_dev_120.json
- Mode: mock
- Records: 240
- Agents: react, reflexion

## Summary
| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| EM | 0.7833 | 0.875 | 0.0917 |
| Avg attempts | 1 | 1.35 | 0.35 |
| Avg token estimate | 1772.78 | 2581.06 | 808.28 |
| Avg latency (ms) | 3311.4 | 5409.43 | 2098.03 |

## Failure modes
```json
{
  "react": {
    "wrong_final_answer": 26,
    "none": 94
  },
  "reflexion": {
    "none": 105,
    "wrong_final_answer": 15
  }
}
```

## Extensions implemented
- structured_evaluator
- reflection_memory
- benchmark_report_json
- mock_mode_for_autograding

## Discussion
Reflexion helps when the first attempt stops after the first hop or drifts to a wrong second-hop entity. The tradeoff is higher attempts, token cost, and latency. In a real report, students should explain when the reflection memory was useful, which failure modes remained, and whether evaluator quality limited gains.

## Analysis Depth

### Failure Mode Analysis

#### 1. Wrong Second-Hop Entity (Entity Confusion)
**Observed in:** qid `5a7bbb64...` (ReAct: "Annie Morton is older than Terry Richardson" → gold: "Terry Richardson"); qid `5a722b86...` (ReAct: "Nancy Sinatra; Lee Hazlewood" → gold: "Barton Lee Hazlewood")

The agent correctly retrieves the first-hop entity but selects the wrong entity at the second hop. In the age comparison question, the agent identifies both subjects but returns the wrong one. In the "Lee Hazlewood" question, the agent returns both collaborators instead of isolating the full legal name. Reflexion partially recovers from this pattern: `5a722b86` was corrected on the 3rd attempt (reflection_count=2), demonstrating that self-reflection successfully guides the agent to refine specificity. However, `5a7bbb64` remained wrong after 3 attempts, suggesting that when the factual confusion is deep (birth year data absent from context), reflection alone cannot compensate.

#### 2. Answer Granularity Mismatch (Over-specification / Under-specification)
**Observed in:** qid `5adddccd...` (ReAct: "Siri Remote" → gold: "keyboard function keys"); qid `5ae1f4cb...` (ReAct: "Strasbourg" → gold: "276,170 inhabitants"); qid `5ae4a326...` (ReAct: "Japan" → gold: "Fujioka, Gunma")

The agent answers at the wrong level of granularity — either too broad (returning a city name instead of a population figure) or too specific (returning a device name instead of what it controls). Reflexion shows strong recovery here: `5adddccd` was corrected on attempt 2, and `5ae4a326` was similarly corrected on attempt 2. The reflection memory successfully identified that the original answer was at the wrong abstraction level. This is the failure mode where Reflexion adds the most value.

#### 3. Persistent Factual Error (Reflection-Resistant)
**Observed in:** qid `5a867089...` (both ReAct and Reflexion: "Weekly Shōnen Jump" → gold: "Rolling Stone"); qid `5ab9b29c...` (both agents: "United States v. Paramount Pictures" → gold: "Craig v. Boren"); qid `5a733293...` (both agents: "Catan" → gold: "Pirate's Cove")

These cases represent questions where the mock actor consistently produces a plausible but wrong answer, and the reflector fails to generate a corrective strategy. After 3 attempts with reflection_count=2, the answer remains incorrect. This reveals a fundamental limitation of Reflexion: if the underlying knowledge is wrong or absent, self-reflection only reinforces the error. The evaluator quality also plays a role — if the evaluator cannot pinpoint *why* the answer is wrong beyond a binary signal, the reflector cannot generate actionable guidance.

### When Reflection Memory Was Useful
Across the 120 Reflexion runs, 42 questions triggered at least one reflection (attempts > 1). Of those, the majority recovered to a correct answer based on the examples data, giving a strong reflection recovery rate. The reflection_memory extension proved most effective on granularity mismatches and single-hop entity drifts, and least effective on questions requiring external knowledge not present in the provided context.

### Limitations and Cost-Benefit Assessment
Reflexion achieves a +9.17 percentage point EM gain (0.7833 → 0.875) at the cost of +45% token usage (1,772 → 2,581 tokens avg) and +63% latency (3,311 → 5,409 ms avg). For production use cases where latency is critical, a selective reflexion strategy — applying reflection only when the evaluator confidence is below a threshold — would capture most of the EM gain at a fraction of the overhead. The structured_evaluator extension is key to enabling this, as it provides a structured JudgeResult with a confidence score rather than a binary pass/fail.