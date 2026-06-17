# Lab 16 — Reflexion Agent

## Tổng quan

Bài lab giúp bạn hiểu và triển khai **Reflexion Agent** — một kiến trúc agent có khả năng tự phản chiếu (self-reflection) để cải thiện câu trả lời qua nhiều lần thử.

Repo cung cấp một scaffold hoàn chỉnh với mock data. Nhiệm vụ của bạn là **thay thế mock bằng LLM thật** và chạy benchmark trên dữ liệu thật.

## Cách hoạt động của Scaffold

Repo sử dụng **Mock Runtime** (`mock_runtime.py`) để giả lập phản hồi LLM:
- `actor_answer()` → trả lời câu hỏi (giả lập)
- `evaluator()` → chấm điểm đúng/sai (giả lập)
- `reflector()` → phân tích lỗi và đề xuất chiến thuật mới (giả lập)

Kết quả mock hoàn toàn deterministic — giúp bạn hiểu flow trước khi tốn chi phí API.

### Chạy thử với mock
```bash
# Cài đặt môi trường
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Chạy benchmark với mock data
python run_benchmark.py --dataset data/hotpot_mini.json --out-dir outputs/sample_run

# Chạy chấm điểm tự động
python autograde.py --report-path outputs/sample_run/report.json
```

## Nhiệm vụ của Học viên

### Bước 1: Hiểu flow (đọc code)
Đọc và hiểu luồng hoạt động trong các file sau:
- `src/reflexion_lab/agents.py` — Vòng lặp chính của ReAct và Reflexion Agent
- `src/reflexion_lab/mock_runtime.py` — Logic giả lập (để biết cần thay thế gì)
- `src/reflexion_lab/schemas.py` — Cấu trúc dữ liệu (có TODO cần hoàn thiện)
- `src/reflexion_lab/prompts.py` — System prompts (có TODO cần viết)

### Bước 2: Hoàn thiện TODO trong scaffold
1. **`schemas.py`**: Định nghĩa các trường cho `JudgeResult` và `ReflectionEntry` (hiện tại là `pass`)
2. **`agents.py`** (dòng 31-35): Triển khai logic Reflexion loop — gọi `reflector()`, cập nhật `reflection_memory`
3. **`prompts.py`**: Viết System Prompt cho Actor, Evaluator, và Reflector

### Bước 3: Thay thế Mock bằng LLM thật
Thay thế 3 hàm trong `mock_runtime.py` bằng LLM call thật:

| Hàm mock | Thay bằng |
|---|---|
| `actor_answer()` | Gửi `ACTOR_SYSTEM` + question + context → LLM → parse câu trả lời |
| `evaluator()` | Gửi `EVALUATOR_SYSTEM` + question + gold_answer + predicted → LLM → parse `JudgeResult` |
| `reflector()` | Gửi `REFLECTOR_SYSTEM` + question + wrong answer + lý do sai → LLM → parse `ReflectionEntry` |

Có thể sử dụng: Ollama, vLLM, OpenAI API, Gemini API, hoặc bất kỳ LLM nào.

### Bước 4: Tạo dữ liệu test và chạy Benchmark

> **Quan trọng:** File `data/hotpot_mini.json` chỉ có 8 câu hỏi và được thiết kế cho mock runtime. Bạn **cần tự tạo thêm dữ liệu test** để kiểm tra implementation của mình.

**Cách tạo dữ liệu test:**
- Tải từ [HotpotQA dataset](https://hotpotqa.github.io/) và chuyển đổi sang format `QAExample`:
  ```json
  {
    "qid": "my_q1",
    "difficulty": "medium",
    "question": "Câu hỏi multi-hop...",
    "gold_answer": "Đáp án đúng",
    "context": [
      {"title": "Nguồn 1", "text": "Thông tin liên quan..."},
      {"title": "Nguồn 2", "text": "Thông tin liên quan..."}
    ]
  }
  ```
- Hoặc tự viết câu hỏi multi-hop của riêng bạn
- Lưu vào `data/` và chạy: `python run_benchmark.py --dataset data/my_test_set.json`

**Yêu cầu tối thiểu:** Chạy benchmark trên ít nhất **100 mẫu** để đạt điểm đầy đủ cho phần Experiment (`autograde.py` kiểm tra `num_records >= 100`).

### Bước 5: Tính toán Token thực tế
Thay thế `token_estimate` và `latency_ms` hardcoded trong `agents.py` bằng giá trị thật từ LLM response.

## Tiêu chí chấm điểm (Rubric)

| Phần | Điểm | Yêu cầu |
|---|---:|---|
| **Core Flow** | **80** | |
| Schema completeness | 30 | Report có đủ các key: `meta`, `summary`, `failure_modes`, `examples`, `extensions`, `discussion` |
| Experiment completeness | 30 | Có cả ReAct + Reflexion, ≥100 records, ≥20 examples chi tiết |
| Analysis depth | 20 | ≥3 failure modes được phân tích, discussion ≥250 ký tự |
| **Bonus** | **20** | Triển khai ≥1 extension (mỗi extension = 10đ, tối đa 20đ) |

**Bonus extensions:** `structured_evaluator`, `reflection_memory`, `adaptive_max_attempts`, `memory_compression`, `mini_lats_branching`, `plan_then_execute`, `benchmark_report_json`, `mock_mode_for_autograding`

## ⏰ Golden Test Set (Bonus cuối ngày)

> Trong **15 phút cuối** của buổi lab, giảng viên sẽ phát một **Golden Test Set** — bộ dữ liệu test mà học viên chưa từng thấy trước đó.
>
> Bạn sẽ chạy agent của mình trên bộ dữ liệu này và nộp kết quả. Điểm từ Golden Test Set sẽ được dùng để **xếp hạng và tính điểm bonus** giữa các nhóm.
>
> **Lưu ý:** Đây là lý do bạn cần đảm bảo agent hoạt động tốt trên **nhiều loại câu hỏi khác nhau**, không chỉ trên `hotpot_mini.json`. Hãy tự tạo dữ liệu test đa dạng để kiểm tra trước!

## Thành phần mã nguồn

| File | Mô tả |
|---|---|
| `src/reflexion_lab/schemas.py` | Kiểu dữ liệu: `QAExample`, `RunRecord`, `JudgeResult`, `ReflectionEntry`, ... |
| `src/reflexion_lab/prompts.py` | Template prompt cho Actor, Evaluator, Reflector **(TODO)** |
| `src/reflexion_lab/mock_runtime.py` | Logic giả lập LLM **(cần thay thế)** |
| `src/reflexion_lab/agents.py` | Vòng lặp chính ReAct + Reflexion Agent **(có TODO)** |
| `src/reflexion_lab/reporting.py` | Xuất báo cáo benchmark |
| `src/reflexion_lab/utils.py` | Helpers: `load_dataset`, `normalize_answer`, `save_jsonl` |
| `run_benchmark.py` | Script chạy đánh giá |
| `autograde.py` | Chấm điểm tự động từ `report.json` |
| `data/hotpot_mini.json` | 8 câu hỏi multi-hop mẫu (dùng cho mock) |
