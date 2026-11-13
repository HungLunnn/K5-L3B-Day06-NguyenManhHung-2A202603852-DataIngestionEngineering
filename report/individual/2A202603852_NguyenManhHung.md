# Báo cáo cá nhân — Day 6

## 1. Dữ liệu và pipeline

- Chủ đề: hướng dẫn sinh viên năm 2025, bao gồm tuyển sinh, học phí, học bổng, kỷ luật, tốt nghiệp và dịch vụ sinh viên.
- Nguồn dữ liệu: corpus demo được tạo trong `starter/data/corpus.json`; không chứa dữ liệu nhạy cảm hay tài liệu không được phép chia sẻ.
- Quy tắc tính trang: dùng 30 trang nội dung có tính năng học thuật, loại bỏ trang bìa, mục lục, trang trống và các phần không chứa nội dung quan trọng. Mỗi phần có `page`, `section`, `year`, `text` và `document_id` rõ ràng.
- Chuẩn hóa: Unicode NFKC, bỏ khoảng trắng thừa, chuẩn hóa xuống dòng, giữ nguyên câu và đoạn văn có ý nghĩa. Không xóa thông tin quan trọng như ngày, số tiền, tên trường, tiêu chuẩn GPA.
- Lỗi/giới hạn: corpus là demo mẫu; không phải tài liệu thực tế của trường. Một số câu hỏi có cùng lĩnh vực nên cần metadata để phân biệt tốt hơn.
- Embedding model/provider: `text-embedding-3-small` qua OpenAI-compatible endpoint `https://api.shopaikey.com/v1` với `OPENAI_API_KEY` trong `starter/.env`. Số chiều embedding phụ thuộc vào phản hồi từ provider; pipeline ghi nhận `dimensions` từ embedding đầu tiên và sử dụng thống nhất cho toàn bộ vector store.
- Vector store: PostgreSQL + pgvector (`0.8.7`) trên Docker local; metric truy xuất là cosine similarity thông qua `embedding <=> query_vector`.
- Lệnh chạy:
  - `cd starter`
  - `python -m src.run`
- Chi phí: chạy demo qua API tương đối thấp vì corpus nhỏ; không có dữ liệu chi phí công khai từ provider nên đánh dấu 0 cho mục đích lab.
- Metadata bắt buộc: `document_id`, `source`, `page`. Trường lọc bổ sung: `section`, `year`. `section` giúp phân biệt các phần như `admission`, `tuition`, `scholarship`, `discipline`. `year` là metadata rõ ràng và ổn định cho dữ liệu năm học.

## 2. Cấu hình và benchmark

### Cấu hình A — fixed-size
- Phương pháp: `fixed_size(page, size=500, overlap=80)`
- Mục tiêu: so sánh hiệu quả khi chunk có kích thước cố định, không phụ thuộc theo phân đoạn logic.

### Cấu hình B — paragraph-based
- Phương pháp: `by_paragraph(page, max_size=400)`
- Mục tiêu: giữ ngữ cảnh theo đoạn / paragraph tốt hơn, giảm cắt giữa ý.

### Cấu hình C — paragraph + filter
- Phương pháp: giống B nhưng chỉ truy xuất với `filter` theo `section` khi câu hỏi có metadata rõ ràng.
- Ví dụ filter: `{ "section": "admission" }`, `{ "section": "scholarship" }`, `{ "section": "tuition" }`
- Khác biệt duy nhất giữa B và C là áp dụng filter đúng ngữ cảnh.

### Benchmark
- Tổng câu hỏi: 20
- Dev: 15, Test: 5
- File benchmark: `starter/data/benchmark.json`
- Mỗi câu đóng vai trò retriever benchmark với:
  - `id`
  - `split`
  - `question`
  - `gold_source_id`
  - `gold_page`
  - `evidence_quote`
  - `expected_answer`
  - `filter` (khi cần)
- Tiêu chí chọn chiến lược đã chốt trước khi xem test: ưu tiên `Hit@1` và `Evidence Hit@3`, sau đó ưu tiên đúng filter metadata và grounding.

## 3. Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---:|---:|---:|---:|---:|---:|
| A_fixed | Dev | 6/15 = 0.40 | 12/15 = 0.80 | ~120 | ~20–30s | 0 |
| A_fixed | Test | 3/5 = 0.60 | 4/5 = 0.80 | ~40 | ~8–12s | 0 |
| B_paragraph | Dev | 6/15 = 0.40 | 12/15 = 0.80 | ~95 | ~20–30s | 0 |
| B_paragraph | Test | 3/5 = 0.60 | 4/5 = 0.80 | ~30 | ~8–12s | 0 |
| C_paragraph_filter | Dev | 12/15 = 0.80 | 15/15 = 1.00 | ~95 | ~20–30s | 0 |
| C_paragraph_filter | Test | 5/5 = 1.00 | 5/5 = 1.00 | ~30 | ~8–12s | 0 |

- File tổng kết: `starter/results/summary.json`
- File trace top-3: `starter/results/trace_top3.json`
- Các trace được lưu theo cấu trúc: `strategy`, `split`, `question_id`, `question`, `filter`, `result`, `top_hits`.

## 4. Phân tích theo năm tiêu chí

### 4.1 Độ chính xác truy xuất
- `C_paragraph_filter` đạt hiệu quả cao nhất trên cả dev và test: `Hit@1` 0.80/0.80 trên dev, 1.00/1.00 trên test, và `Evidence Hit@3` bằng 1.0 ở cả hai tập.
- `A_fixed` và `B_paragraph` có cùng kết quả vì cả hai cùng không áp dụng filter ở phần lớn câu hỏi, dẫn tới nhầm lẫn giữa các phần có cùng từ khóa nhưng khác `section`.

### 4.2 Tính mạch lạc của chunk
- B và C dùng `by_paragraph` giữ được ý đoạn rõ hơn so với fixed-size, nhưng trong corpus demo này, hiệu quả khác biệt không quá lớn khi câu hỏi dễ tìm. Cải thiện lớn nhất từ việc dùng metadata filter.
- Có thể nhận ra rằng fixed-size đôi khi cắt ngang giữa câu và làm mất bối cảnh, dù không quá nghiêm trọng cho benchmark đơn giản.

### 4.3 Tính hữu dụng của metadata
- Metadata `section` rất quan trọng. Với câu hỏi như "Hạn nộp hồ sơ xét tuyển là ngày nào?", nếu không lọc theo `section=admission` thì hệ thống có thể lấy đoạn từ `scholarship`, `tuition`, hoặc `orientation` nếu chứa các từ tương tự hoặc bị nhầm lẫn vì keyword không rõ.
- Filter đã cải thiện độ chính xác rõ rệt trong C.

### 4.4 Grounding quality
- `C_paragraph_filter` cho thấy top-3 luôn chứa ít nhất một đoạn có evidence đủ để trả lời hoặc tương ứng với gold page/source. Điều này tương đồng với kết quả `Evidence Hit@3 = 1.0`.
- Với `A_fixed` và `B_paragraph`, một số câu test không có gold trong top-3 do sự chồng chéo giữa các phần và thiếu bộ lọc.

### 4.5 Tác động chiến lược dữ liệu
- So sánh A–B: không có sự cải thiện đáng kể khi chỉ biến đổi chunking; cả hai tương đồng vì corpus khá ngắn và câu hỏi dễ.
- So sánh B–C: đóng góp chính đến hiệu suất đến từ metadata filter. Cho thấy trong một corpus có cấu trúc, filter là yếu tố quyết định hơn là chunking đơn thuần.

## 5. Kết luận

- Chiến lược tốt nhất là `C_paragraph_filter` vì cho hiệu suất cao nhất và nhất quán trong cả dev/test.
- Nếu tổng quát hóa, có thể nói rằng trong corpus học thuật / chính sách / handbook, chunking theo đoạn + metadata filter là lựa chọn mạnh hơn so với fixed-size hoặc không filter.
- Hạn chế của báo cáo hiện tại: corpus demo nhỏ, benchmark 20 câu chưa quá lớn, chưa thực hiện chấm thủ công coherence / grounding độ sâu theo thang 0–2 cho 10 vị trí; thời gian và chi phí chỉ là ước lượng sơ bộ trong môi trường lab.
- Nếu làm lại, tôi sẽ bổ sung: (1) thêm nhiều câu hỏi khó và test mới, (2) đánh giá thủ công coherence ở 10 vị trí cùng nhau, (3) lưu log thời gian thực tế và chi phí API, (4) so sánh thêm chiến lược hybrid hoặc BM25.

## 6. Tài liệu liên quan
- `starter/data/corpus.json`
- `starter/data/benchmark.json`
- `starter/results/summary.json`
- `starter/results/trace_top3.json`
- `starter/src/run.py`
- `GUIDE.md`
- `BENCHMARK.md`
