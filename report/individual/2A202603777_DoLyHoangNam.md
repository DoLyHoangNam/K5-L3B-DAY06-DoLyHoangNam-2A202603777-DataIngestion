# Báo cáo cá nhân — Day 6

- **Họ và tên:** Đỗ Lý Hoàng Nam
- **MSSV:** 2A202603777

## Dữ liệu và pipeline
- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:**
  - Chủ đề: Kinh tế Việt Nam & các chuyên đề chính sách (World Bank *Taking Stock*, 2023 & 2025).
  - Nguồn & giấy phép: World Bank Open Knowledge / Documents & Reports (`documents1.worldbank.org`), giấy phép mở CC BY 3.0 IGO / CC BY 4.0 (xem trang 4 mỗi tài liệu).
    1. `wb-taking-stock-2023-08` (*Taking Stock August 2023: Making Public Investment Work for Growth*, `starter/data/taking_stock_2023_08.pdf`): 58 trang vật lý → **40 trang nội dung** (trang 11–17, 19–37, 39–52).
    2. `wb-taking-stock-2025-03` (*Taking Stock March 2025: Electrifying Journeys - E-mobility Transition in Viet Nam*, `starter/data/taking_stock_2025_03.pdf`): 62 trang vật lý → **48 trang nội dung** (trang 11–17, 19–40, 42–60).
  - **Tổng cộng:** **88 trang nội dung hữu ích** trên 120 trang vật lý (chi tiết từng trang xem [data/manifest.json](../../data/manifest.json)).
  - Quy tắc tính trang: Chỉ tính các trang PDF vật lý chứa nội dung phân tích thực chất (Overview/Executive Summary, Chapter 1, Chapter 2); loại trừ bìa, trang trống, trang bản quyền, mục lục/danh mục hình-bảng/từ viết tắt, lời cảm ơn, trang chia chương chỉ có tiêu đề, tài liệu tham khảo và colophon.
- **Chuẩn hóa, lỗi và giới hạn:**
  - Chuẩn hóa Unicode NFC (`unicodedata.normalize("NFC")`), chuẩn hóa `\r\n` → `\n`, gộp khoảng trắng/tab thừa trên từng dòng nhưng giữ nguyên ngắt đoạn (`\n\n`).
  - Không có trang rỗng/lỗi đọc trong 88 trang nội dung (`empty_or_error_pages: []` trong [results/ingest_log.json](../../results/ingest_log.json)).
  - Giới hạn trích xuất PDF: `pypdf==6.21.4` giữ nguyên ngắt dòng vật lý của bố cục 2 cột/biểu đồ và đôi khi tách từ có dấu gạch nối qua dòng (vd: `economy- wide` ở trang 16 báo cáo 2025) hoặc lẫn nhãn biểu đồ vào mạch văn.
- **Embedding model/provider/version/số chiều, vector store/version, metric, lệnh chạy và chi phí:**
  - Embedding: Google Gemini `gemini-embedding-001` qua SDK `google-genai==3.3.0`, **3072 chiều** (`task_type="RETRIEVAL_DOCUMENT"` cho chunk, `"RETRIEVAL_QUERY"` cho câu hỏi).
  - Vector store: PostgreSQL `16.16` + `pgvector==0.8.7` (Docker `pgvector/pgvector:0.8.7-pg16`, cổng local `127.0.0.1:55433`), truy xuất **exact cosine distance** (`embedding <=> query_vector`), lưu bền vững với `ON CONFLICT DO UPDATE` và xóa chunk cũ khi nạp lại (đã kiểm chứng nạp lại strategy B: trước 361 dòng, sau 361 dòng).
  - Chi phí: **\$0** (dùng Gemini API Free Tier; tổng 919 chunk + 20 câu hỏi + 1 probe, có retry 62s khi gặp giới hạn 100 requests/phút).
  - Lệnh chạy từ `starter/`:
    ```powershell
    docker compose -p day6_student_starter up -d --wait
    .\.venv\Scripts\python.exe scripts\check_setup.py
    .\.venv\Scripts\python.exe -m src.run
    .\.venv\Scripts\python.exe scripts\analyze_results.py
    ```
- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn:**
  - Bắt buộc: `document_id` (TEXT), `source` (TEXT), `page` (INTEGER).
  - Bổ sung: `year` (INTEGER: `2023` hoặc `2025`) và `section` (TEXT: `overview`, `economic_developments`, `special_topic`), lấy trực tiếp từ thông tin xuất bản và cấu trúc chương của 2 báo cáo trong `data/manifest.json`. Chọn `year` và `section` vì 2 báo cáo có nhiều nội dung kinh tế vĩ mô trùng chủ đề (tăng trưởng GDP, đầu tư công, tiêu dùng) nhưng khác năm, nên filter giúp tránh nhầm số liệu giữa các năm.

## Cấu hình và benchmark
- **A / B / C (tham số cụ thể, khác biệt duy nhất B–C):**
  - **A:** `fixed_size(size=500, overlap=50)`, không dùng filter.
  - **B:** `by_paragraph(max_size=800)` (gom đoạn theo `\n\n`, cắt đoạn quá dài ở ranh giới câu), không dùng filter.
  - **C:** Chunking **giống hệt B** (`by_paragraph(max_size=800)`), **khác biệt duy nhất** là áp dụng SQL metadata filter (`WHERE year = ...` / `section = ...`) khi câu hỏi có trường `filter`.
- **≥20 câu: phân chia ≥15 dev / ≥5 test, câu metadata filter và cách kiểm chứng evidence:**
  - Bộ [benchmark/questions.json](../../benchmark/questions.json) gồm **20 câu**: **15 dev** (`q01`–`q15`) và **5 test** (`q16`–`q20`), phủ các dạng: trực tiếp (`truc_tiep`), diễn đạt lại (`dien_dat_lai`), điều kiện/ngoại lệ (`dieu_kien_ngoai_le`) và lọc metadata (`metadata_filter`).
  - Có **4 câu dùng filter**: 3 câu `dev` (`q03` `year=2023`, `q09` `year=2025`, `q14` `year=2025, section=special_topic`) và 1 câu `test` (`q19` `year=2025`). Không đưa `gold_source_id` hay đáp án vào filter.
  - Kiểm chứng evidence: Chạy script đối chiếu tự động 100% `evidence_quote` tồn tại nguyên văn trong text đã chuẩn hóa của `gold_page` trước khi chạy pipeline.
- **Tiêu chí chọn chiến lược đã chốt trước khi xem test:**
  - So sánh A, B, C trên tập `dev`: ưu tiên **Evidence Hit@3** cao nhất → nếu bằng nhau xét **Hit@1** → sau đó xét **độ mạch lạc (Coherence)**, **tuân thủ filter** và **số chunk/chi phí**.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---:|---:|---:|---:|---|
| A | dev | 4/15 (26.7%) | 8/15 (53.3%) | 558 | 395.69s | \$0 (Free Tier) |
| A | test | 2/5 (40.0%) | 2/5 (40.0%) | 558 | — | \$0 |
| B | dev | 2/15 (13.3%) | 6/15 (40.0%) | 361 | 273.12s | \$0 (Free Tier) |
| B | test | 1/5 (20.0%) | 2/5 (40.0%) | 361 | — | \$0 |
| C | dev | 2/15 (13.3%) | 6/15 (40.0%) | 361 | 0.79s *(dùng lại vector B)* | \$0 |
| C | test | 1/5 (20.0%) | 2/5 (40.0%) | 361 | — | \$0 |

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---:|---:|---:|---|
| A | 0.50 / 2 (10) | 15/15 | N/A | 0: 1, 1: 2, 2: 2 — TB **1.20 / 2** |
| B | 1.00 / 2 (10) | 15/15 | N/A | 0: 2, 1: 0, 2: 3 — TB **1.20 / 2** |
| C | 1.00 / 2 (10) | 15/15 | 1/1 (test) | 0: 2, 1: 0, 2: 3 — TB **1.20 / 2** |

- **Đường dẫn trace, nhãn thủ công và cách chọn mẫu:**
  - Traces: [results/traces_A.jsonl](../../results/traces_A.jsonl), [results/traces_B.jsonl](../../results/traces_B.jsonl), [results/traces_C.jsonl](../../results/traces_C.jsonl), [results/metrics.json](../../results/metrics.json), [results/chunk_stats.json](../../results/chunk_stats.json), [results/ingest_log.json](../../results/ingest_log.json).
  - Nhãn thủ công (tác giả tự chấm): [results/audit_coherence.csv](../../results/audit_coherence.csv), [results/audit_metadata.csv](../../results/audit_metadata.csv), [results/audit_grounding.csv](../../results/audit_grounding.csv).
  - Cách chọn mẫu coherence: chọn cố định slot `c001` trên 10 trang nội dung đầu tiên của `wb-taking-stock-2023-08` (trang 11–17, 19–21) trước khi xem điểm để kiểm tra hành vi tại ranh giới cắt đầu tiên của mỗi trang.
  - Ghi nhận thiên lệch: người chấm đồng thời là tác giả bộ câu hỏi và pipeline.

## Phân tích và kết luận
- **So sánh A–B và B–C; 2 ví dụ sai có ID câu và nguồn:**
  - **A vs B (tác động của chunking):** Trên `dev`, A đạt Evidence Hit@3 cao hơn B (**8/15** so với **6/15**), do cửa sổ 500 ký tự tập trung hơn vào một ý ngắn nên vector embedding ít bị loãng bởi các câu xung quanh hoặc nhãn biểu đồ. Ngược lại, A cắt giữa từ ở **8/10** vị trí mẫu (coherence **0.50/2**), còn B/C không cắt giữa từ và giữ được câu hoàn chỉnh (**1.00/2**), đồng thời giảm **35.3% số chunk** (361 vs 558).
  - **B vs C (tác động của metadata filter):** Trên tập `dev` và `test`, Hit@1/Hit@3 của B và C bằng nhau vì câu cần lọc đã có độ tương đồng cao sẵn ở top-1. Tuy nhiên, kiểm tra trace cho thấy filter ở C **loại bỏ hoàn toàn kết quả sai năm** ở vị trí #2 của `q03` (`year=2023`, B lọt `wb-taking-stock-2025-03` trang 15) và vị trí #2 của `q09` (`year=2025`, B lọt `wb-taking-stock-2023-08` trang 33).
  - **Ví dụ lỗi cụ thể:**
    1. **`q20` (test, nguồn `wb-taking-stock-2025-03` trang 58) ở Strategy A:** `fixed_size` cắt đôi câu liệt kê 5 bộ ngành và EVN giữa rank #1 (`"with Viet Nam Electricity an additional key stakeholder..."`) và rank #2 (`"A cross-ministerial steering committee..."`), làm A trượt cả Hit@3 (`False`), trong khi B và C giữ nguyên đoạn nên đạt Hit@1 (`True`) và Grounding 2/2.
    2. **`q16` (test, nguồn `wb-taking-stock-2023-08` trang 11) ở cả A, B, C:** Rank #1 trả về trang 19 chứa nhãn biểu đồ (`"2023f (Jun-23)... Figure 1.2. Global goods trade growth"`) thay vì đoạn văn xuôi trang 11 ghi dự báo 2.1% và 1.7%, do PDF trích lẫn chữ trong hình/biểu đồ có nhiều từ khóa giống câu hỏi.
    3. *(Bổ sung ghi nhận từ audit)* **`q19` (test, `wb-taking-stock-2025-03`):** B và C tìm ra trang 19 chứa đầy đủ số liệu 54% vs 61.7% và lý do tiết kiệm hộ gia đình (Grounding **2/2**), nhưng chỉ số tự động đánh `False` vì `gold_page` ban đầu chỉ ghi trang 11 (Executive Summary).
- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:**
  - Theo tiêu chí đã chốt trước khi xem test (ưu tiên `Hit@3` trên `dev`), **chiến lược A** đạt điểm truy xuất `dev` cao nhất (**8/15** vs **6/15**), nhưng đánh đổi mạnh về độ mạch lạc (0.50/2, hay cắt ngang câu như `q20`) và tốn nhiều chunk hơn (+54.6% số chunk so với B/C).
  - Trong thực tế sản xuất cho tài liệu đa năm có nhiều số liệu dễ nhầm lẫn, nên chọn **kiến trúc của C** (chunking theo cấu trúc + metadata filter) nhưng **giảm `max_size` xuống ~450–500 ký tự** để kết hợp độ nhạy tìm kiếm của A với độ sạch câu chữ và tính an toàn theo năm của C.
- **Hạn chế của dữ liệu, nhãn, test nhỏ, đo thời gian/chi phí:**
  - Tập `test` chỉ có 5 câu (mỗi câu chiếm 20%) nên độ tin cậy thống kê thấp; kết quả chỉ mang tính minh họa trên 2 báo cáo World Bank.
  - Văn bản PDF có nhiều biểu đồ/chú thích chân trang khiến `pypdf` trộn nhãn hình vào đoạn văn.
  - Thời gian ingest của A và B bao gồm các khoảng ngủ 62 giây do giới hạn 100 requests/phút của Gemini Free Tier.
- **Nếu làm lại hoặc mở rộng, cải tiến gì?**
  - Lọc bỏ dòng tiêu đề/chú thích biểu đồ khi ingest PDF và nối các từ bị ngắt gạch nối qua dòng (`economy-\nwide` → `economy-wide`).
  - Thử `by_paragraph(max_size=500)` kết hợp hybrid search (BM25 + pgvector cosine) để xử lý tốt hơn các câu hỏi có số liệu cụ thể như `q03`, `q16`.
  - Hỗ trợ nhiều trang hợp lệ hơn trong `gold_page` khi thông tin lặp lại ở cả Executive Summary và Chapter 1.
