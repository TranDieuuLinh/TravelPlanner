# Information Finder answer evals

Cập nhật lần cuối: 2026-08-10.

`cases.json` chứa bộ eval nhỏ Việt–Anh cho giờ mở cửa, giá vé, địa điểm,
nguồn mâu thuẫn, thiếu nguồn, cross-lingual và prompt injection trong source.
Test offline kiểm tra invariant thay vì khớp nguyên câu: source ID hợp lệ,
citation được render, thuật ngữ bắt buộc và policy coi source là dữ liệu không
đáng tin cậy.

Shared LLM client hiện chỉ trả text, chưa trả usage metadata. Vì vậy eval offline
không giả lập token usage. Adapter ghi latency và số nguồn bằng metadata an toàn;
khi shared client expose usage, eval live cần thu thập latency/token mà không lưu
prompt hoặc source content. Live eval không chạy mặc định và không tiêu API credit
trong CI.
