from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.modules.auth.security import hash_password
from app.modules.marketplace.model import MarketplacePlan, MarketplacePlanVersion
from app.modules.users.model import User


def seed_demo_marketplace(db: Session) -> None:
    # Check if demo listings already exist
    existing = db.query(MarketplacePlan).filter_by(status="published").first()
    if existing:
        return

    # 1. Ensure a demo creator user exists
    creator = db.query(User).filter_by(email="creator@example.com").first()
    if not creator:
        creator = User(
            email="creator@example.com",
            full_name="Lê Minh Châu (Local Creator)",
            role="creator",
            status="active",
            creator_status="verified",
            password_hash=hash_password("Password123!"),
            bio="Chuyên gia lịch trình trải nghiệm địa phương miền Trung & Tây Nguyên.",
            avatar_url="https://images.unsplash.com/photo-1534528741775-53994a69daeb",
        )
        db.add(creator)
        db.flush()

    demo_listings = [
        {
            "id": "mp_demo_danang",
            "title": "Đà Nẵng & Hội An 4 ngày 3 đêm - Ẩm thực & Văn hóa",
            "description": "Lịch trình trọn vẹn khám phá thành phố đáng sống Đà Nẵng, check-in Cầu Vàng Bà Nà Hills và dạo phố cổ Hội An về đêm.",
            "destination": "Đà Nẵng - Hội An",
            "duration_days": 4,
            "category": "food",
            "price_amount": 149000,
            "media_urls": ["https://images.unsplash.com/photo-1559592413-7cec4d0cae2b"],
            "highlights": ["Check-in Cầu Vàng Bà Nà Hills", "Thưởng thức Cao Lầu & Mì Quảng chính gốc", "Thả đèn hoa đăng trên sông Hoài"],
            "day_summaries": [
                {"day": 1, "theme": "Đón sân bay & Dạo biển Mỹ Khê"},
                {"day": 2, "theme": "Khám phá Bà Nà Hills & Cầu Vàng"},
                {"day": 3, "theme": "Tham quan phố cổ Hội An"},
                {"day": 4, "theme": "Mua sắm quà lưu niệm & Tiễn sân bay"},
            ],
        },
        {
            "id": "mp_demo_phuquoc",
            "title": "Phú Quốc biển ngọc & ngắm hoàng hôn 3 ngày",
            "description": "Lịch trình thư giãn nghỉ dưỡng, lặn ngắm san hô tại Nam Đảo và ngắm hoàng hôn Sunset Sanato nổi tiếng.",
            "destination": "Phú Quốc",
            "duration_days": 3,
            "category": "nature",
            "price_amount": 199000,
            "media_urls": ["https://images.unsplash.com/photo-1540555700478-4be289fbecef"],
            "highlights": ["Cáp treo Hòn Thơm dài nhất thế giới", "Lặn ngắm san hô hòn Mây Rút", "Tiệc nướng hải sản chợ đêm Phú Quốc"],
            "day_summaries": [
                {"day": 1, "theme": "Check-in khách sạn & Ngắm hoàng hôn"},
                {"day": 2, "theme": "Tour 4 đảo & Lặn ngắm san hô"},
                {"day": 3, "theme": "Tham quan cơ sở sản xuất nước mắm & Tiễn sân bay"},
            ],
        },
        {
            "id": "mp_demo_hanoi",
            "title": "Hà Nội 36 phố phường & Foodtour 2 ngày",
            "description": "Khám phá chiều sâu văn hóa Thăng Long, thưởng thức Phở gia truyền, Cà phê trứng và bún chả Hà Nội.",
            "destination": "Hà Nội",
            "duration_days": 2,
            "category": "food",
            "price_amount": 99000,
            "media_urls": ["https://images.unsplash.com/photo-1509030450996-939a26352132"],
            "highlights": ["Foodtour phố cổ Hà Nội", "Thưởng thức Cà phê trứng Đinh", "Viếng Lăng Bác & Hồ Hoàn Kiếm"],
            "day_summaries": [
                {"day": 1, "theme": "Foodtour 36 phố phường & Hồ Tây"},
                {"day": 2, "theme": "Di tích lịch sử & Mua đặc sản Ô mai"},
            ],
        },
        {
            "id": "mp_demo_dalat",
            "title": "Đà Lạt săn mây & Cafe ngắm đồi thông 3 ngày",
            "description": "Hành trình thơ mộng săn mây Cầu Đất, check-in các quán cafe view thung lũng đẹp nhất Đà Lạt.",
            "destination": "Đà Lạt",
            "duration_days": 3,
            "category": "family",
            "price_amount": 129000,
            "media_urls": ["https://images.unsplash.com/photo-1506744038136-46273834b3fb"],
            "highlights": ["Săn mây thung lũng Cầu Đất", "Hái dâu tây tại vườn", "Dạo chợ đêm & Thưởng thức lẩu gà lá é"],
            "day_summaries": [
                {"day": 1, "theme": "Đón bến xe & Cafe view đồi thông"},
                {"day": 2, "theme": "Săn mây Cầu Đất & Chợ đêm Đà Lạt"},
                {"day": 3, "theme": "Thung lũng Tình Yêu & Khởi hành về"},
            ],
        },
    ]

    now = datetime.now(timezone.utc)

    for item in demo_listings:
        plan = MarketplacePlan(
            id=item["id"],
            creator_id=creator.id,
            status="published",
            current_published_version_id=f"{item['id']}_v1",
        )
        db.add(plan)

        version = MarketplacePlanVersion(
            id=f"{item['id']}_v1",
            marketplace_plan_id=item["id"],
            version=1,
            source_plan_id=f"source_{item['id']}",
            source_plan_version_id=f"source_ver_{item['id']}",
            title=item["title"],
            description=item["description"],
            destination=item["destination"],
            duration_days=item["duration_days"],
            category=item["category"],
            price_amount=item["price_amount"],
            price_currency="VND",
            media_urls=item["media_urls"],
            preview_snapshot={
                "title": item["title"],
                "destination": item["destination"],
                "days": item["duration_days"],
                "highlights": item["highlights"],
                "daySummaries": item["day_summaries"],
            },
            moderation_status="published",
            published_at=now,
        )
        db.add(version)

    db.commit()
