# ADR-023: Tính thống kê vùng trực tiếp từ catalog Place

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-05

## Bối cảnh

Planner cần thống kê theo vùng để tạo trip themes. Trước đây cùng metrics được
lưu trong `place_region_snapshots` và con trỏ mutable
`place_region_catalog_state`. Hai bảng này sao chép dữ liệu có thể dựng lại từ
catalog Knowledge Graph, tạo thêm state và quy trình refresh phải đồng bộ.

## Quyết định

- Xóa `place_region_snapshots` và `place_region_catalog_state`.
- Tính region metrics trực tiếp từ KG place entity thuộc `region_key` được yêu cầu và các
  vùng con.
- Giữ `RegionSnapshotReference` làm contract truy vết runtime. `snapshotId` và
  `catalogVersion` được suy ra xác định từ fingerprint của catalog thay vì là
  identity của một row PostgreSQL.
- Planning-run tiếp tục lưu input/output từng stage để truy vết kết quả đã dùng.

## Hệ quả

- Loại bỏ hai bảng và state refresh có thể bị lệch khỏi catalog.
- Planner luôn nhìn thấy dữ liệu KG place entity hiện tại của đúng vùng.
- Mỗi planning request phải tính metrics trong memory; nếu catalog tăng lớn,
  cần đo trước khi bổ sung một lớp cache không thuộc persistence contract.
- Không thể truy vấn nguyên JSON snapshot lịch sử từ bảng region snapshot;
  planning-run là nguồn audit cho kết quả Planner đã dùng.
