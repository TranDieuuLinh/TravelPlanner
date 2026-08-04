from app.shared.errors import AppError


def ensure_creator_role(user_role: str) -> None:
    if user_role != "creator":
        raise AppError(403, "CREATOR_REQUIRED", "Chỉ tài khoản creator mới có quyền thực hiện hành động này.")


def ensure_admin_role(user_role: str) -> None:
    if user_role != "admin":
        raise AppError(403, "ADMIN_REQUIRED", "Chỉ tài khoản admin mới có quyền thực hiện hành động này.")


def ensure_listing_ownership(creator_id: int, actor_id: int) -> None:
    if creator_id != actor_id:
        raise AppError(404, "LISTING_NOT_FOUND", "Không tìm thấy listing hoặc bạn không có quyền sở hữu.")


def validate_submittable_version(
    title: str,
    description: str,
    category: str,
    price_amount: int,
    media_urls: list[str],
    preview_snapshot: dict,
    check_status: str,
    plan_status: str,
) -> None:
    if plan_status != "locked" or check_status != "valid":
        raise AppError(400, "PLAN_NOT_ELIGIBLE", "Plan chưa đạt tiêu chuẩn để đăng (phải locked và valid).")
    if not title.strip():
        raise AppError(422, "MISSING_TITLE", "Tiêu đề listing không được để trống.", {"title": "Tiêu đề bắt buộc."})
    if not description.strip():
        raise AppError(422, "MISSING_DESCRIPTION", "Mô tả listing không được để trống.", {"description": "Mô tả bắt buộc."})
    if price_amount <= 0:
        raise AppError(422, "INVALID_PRICE", "Giá bán phải lớn hơn 0.", {"priceAmount": "Giá phải lớn hơn 0."})
    if not preview_snapshot:
        raise AppError(400, "MISSING_PREVIEW", "Plan chưa có thông tin preview.")


def ensure_publishable_status(moderation_status: str) -> None:
    if moderation_status != "approved":
        raise AppError(400, "VERSION_NOT_APPROVED", f"Chỉ phiên bản đã được duyệt mới có thể phát hành (hiện tại: {moderation_status}).")
