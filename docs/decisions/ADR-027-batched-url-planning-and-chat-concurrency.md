# ADR-027: Batch URL planning và concurrency theo chat

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-06

## Bối cảnh

Mỗi URL trong một lần gửi từng có thể kích hoạt toàn bộ Explorer và Planner,
trong khi một worker FIFO toàn cục khiến chat không liên quan phải chờ. Tăng
worker mà không khóa theo chat sẽ tạo nhiều writer cạnh tranh cùng revision.

## Quyết định

- Giữ một durable source job cho mỗi URL nhưng dùng `batchId` làm đơn vị
  finalization: một Explorer/Planner run nhận tất cả URL/ảnh của batch.
- Cho phép nhiều worker slot xử lý các chat khác nhau đồng thời; mỗi `chatId`
  chỉ có tối đa một job `running`.
- Batch thành công hoặc thất bại cùng nhau và dùng chung revision kết quả.
- Cache Google fallback trong process bằng TTL + giới hạn kích thước, bên ngoài
  semaphore Playwright.
- Chỉ tái sử dụng theme khi hai projection canonical TripIntent và TripSpec
  không đổi; các stage chọn địa điểm, route và check vẫn chạy lại.
- Commit Explorer source/review snapshot trước KG enrichment phụ để lỗi
  enrichment không rollback critical hand-off.
- Supervisor chỉ được chuyển tiếp planning arguments có schema; service chiếu
  chúng thành intake patch nội bộ và vẫn sở hữu validation, authorization cùng
  persistence. Contract classifier-only chi tiết được thay thế bởi ADR-029.

## Hệ quả

- N URL trong một request chỉ trả chi phí lập plan một lần.
- Chat A xử lý media không chặn chat B, nhưng hai request ghi cùng chat vẫn tuần
  tự và tránh conflict revision chủ động.
- Trạng thái từng source vẫn quan sát/retry được, còn kết quả planning mang tính
  nguyên tử theo batch.
- Cache Google hiện chỉ dùng chung trong một process; deployment nhiều replica
  muốn cache dùng chung phải bổ sung store phân tán sau.
- Enrichment lỗi không chặn plan nhưng cần telemetry/retry vận hành dựa trên
  `enrichmentDegraded`.
