# ADR-001: Kiến trúc nguyên khối theo mô-đun với FastAPI và PostgreSQL

- Trạng thái: Đã chấp nhận
- Ngày: 2026-07-27

## Bối cảnh

Sản phẩm bao gồm Planner, Marketplace, thanh toán, cộng tác và vận hành, nhưng
kho mã và đội ngũ cần khả năng phát triển nhanh cùng transaction nhất
quán. Backend hiện đã sử dụng FastAPI, Pydantic, SQLAlchemy, Alembic và
PostgreSQL. SQLite chỉ còn được dùng cho test cô lập trong bộ nhớ.

## Quyết định

Tiếp tục sử dụng modular monolith Python FastAPI với PostgreSQL.

- Tổ chức code theo module nghiệp vụ.
- Giữ ranh giới router, service/workflow, domain, repository và integration.
- Sử dụng SQLAlchemy và Alembic cho lưu trữ và migration.
- Chỉ PostgreSQL được chấp nhận trong `DATABASE_URL` của runtime. Container
  backend phải chạy Alembic thành công trước khi khởi động FastAPI.
- Không dùng database bảo trì mặc định `postgres` cho runtime, migration hoặc
  test tích hợp. Mỗi môi trường dùng database ứng dụng riêng; cấu hình hiện tại
  dùng `vsf_travel`. Settings phải fail fast khi `DATABASE_URL` trỏ tới
  `postgres`.
- Thêm cơ chế background job trong cùng hệ thống deploy trước khi cân nhắc tách
  service.
- Đặt integration với provider sau interface.

## Hệ quả

- Phát triển và vận hành trên máy cá nhân vẫn đơn giản.
- Transaction liên module như từ order đến entitlement dễ được bảo vệ hơn.
- Ranh giới module cần kỷ luật vì deployment không tự ép buộc các ranh giới này.
- Tác vụ AI/import/route chạy lâu cần worker và trạng thái job rõ ràng.
- Vẫn có thể tách service khi có bằng chứng về nhu cầu scale hoặc ownership độc
  lập.
