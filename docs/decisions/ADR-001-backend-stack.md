# ADR-001: Kiến trúc nguyên khối theo mô-đun với FastAPI và PostgreSQL

- Trạng thái: Đã chấp nhận
- Ngày: 2026-07-27

## Bối cảnh

Sản phẩm bao gồm Planner, Marketplace, thanh toán, cộng tác và vận hành, nhưng
kho mã và đội ngũ cần khả năng phát triển nhanh cùng transaction nhất
quán. Backend hiện đã sử dụng FastAPI, Pydantic, SQLAlchemy, Alembic và
PostgreSQL/SQLite.

## Quyết định

Tiếp tục sử dụng modular monolith Python FastAPI với PostgreSQL.

- Tổ chức code theo module nghiệp vụ.
- Giữ ranh giới router, service/workflow, domain, repository và integration.
- Sử dụng SQLAlchemy và Alembic cho lưu trữ và migration.
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
