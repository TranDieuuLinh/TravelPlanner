"""add curated destination region stories

Revision ID: 20260810_0048
Revises: 20260807_0047
Create Date: 2026-08-10
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op


revision: str = "20260810_0048"
down_revision: str | None = "20260807_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


HANOI_REGION_STORIES = [
    {
        "id": "vn-ha-noi-history",
        "region_key": "vn,ha-noi",
        "story_type": "destination_history",
        "text": (
            "Hà Nội có hơn một nghìn năm lịch sử. Năm 1010, vua Lý Thái Tổ "
            "chọn nơi đây làm kinh đô và đặt tên là Thăng Long, nghĩa là “Rồng "
            "bay lên”. Các triều đại, thời kỳ Pháp thuộc, chiến tranh và quá "
            "trình hiện đại hóa đã tạo nên một thành phố nhiều lớp lang như ngày nay."
        ),
        "source_url": (
            "https://english.hanoi.gov.vn/district-district-town/"
            "geographical-introduction-and-overview-265511023.htm"
        ),
        "evidence_types": ["webpage"],
        "sort_order": 10,
    },
    {
        "id": "vn-ha-noi-traffic",
        "region_key": "vn,ha-noi",
        "story_type": "destination_traffic",
        "text": (
            "Giao thông ở Hà Nội đông đúc và khó đoán. Các phương tiện có thể "
            "xuất hiện từ những hướng bất ngờ, vì vậy hãy quan sát kỹ — kể cả "
            "trên đường một chiều — và chỉ sang đường khi an toàn."
        ),
        "source_url": "https://www.gov.uk/guidance/living-in-vietnam",
        "evidence_types": ["webpage"],
        "sort_order": 20,
    },
    {
        "id": "vn-ha-noi-transport",
        "region_key": "vn,ha-noi",
        "story_type": "destination_transport",
        "text": (
            "Hãy sử dụng Grab hoặc Xanh SM. Trước khi lên xe, hãy xác nhận biển "
            "số, phương tiện và tài xế khớp với thông tin trong ứng dụng."
        ),
        "source_url": (
            "https://www.gov.uk/foreign-travel-advice/vietnam/safety-and-security"
        ),
        "evidence_types": ["webpage"],
        "sort_order": 30,
    },
    {
        "id": "vn-ha-noi-water",
        "region_key": "vn,ha-noi",
        "story_type": "destination_water",
        "text": (
            "Không uống nước máy. Hãy chọn nước đóng chai còn nguyên niêm phong "
            "hoặc nước đã được xử lý đạt yêu cầu, đồng thời thận trọng với đá."
        ),
        "source_url": "https://www.cdc.gov/yellow-book/hcp/asia/vietnam.html",
        "evidence_types": ["webpage"],
        "sort_order": 40,
    },
    {
        "id": "vn-ha-noi-security",
        "region_key": "vn,ha-noi",
        "story_type": "destination_security",
        "text": (
            "Hãy kéo khóa túi và giữ túi ở phía trước khi ở Phố Cổ, chợ và trên "
            "phương tiện công cộng. Chú ý các xe máy đi tới từ phía sau."
        ),
        "source_url": "https://www.smartraveller.gov.au/destinations/asia/vietnam",
        "evidence_types": ["webpage"],
        "sort_order": 50,
    },
    {
        "id": "vn-ha-noi-pricing",
        "region_key": "vn,ha-noi",
        "story_type": "destination_pricing",
        "text": (
            "Hãy thống nhất toàn bộ mức giá và dịch vụ trước khi đi xích lô hoặc "
            "sử dụng một dịch vụ không chính thức."
        ),
        "source_url": "https://www.smartraveller.gov.au/destinations/asia/vietnam",
        "evidence_types": ["webpage"],
        "sort_order": 60,
    },
    {
        "id": "vn-ha-noi-etiquette",
        "region_key": "vn,ha-noi",
        "story_type": "destination_etiquette",
        "text": (
            "Hãy che vai và đầu gối khi tham quan đền, chùa và các địa điểm văn "
            "hóa, đồng thời làm theo hướng dẫn được niêm yết tại lối vào."
        ),
        "source_url": (
            "https://www.gov.uk/foreign-travel-advice/vietnam/safety-and-security"
        ),
        "evidence_types": ["webpage"],
        "sort_order": 70,
    },
    {
        "id": "vn-ha-noi-train-safety",
        "region_key": "vn,ha-noi",
        "story_type": "destination_train_safety",
        "text": (
            "Phố đường tàu là tuyến đường sắt vẫn đang hoạt động. Tuyệt đối "
            "không vượt rào chắn, đứng trên đường ray hoặc phớt lờ các quy định "
            "hiện hành của địa phương."
        ),
        "source_url": "https://vietnamtourism.vn/en/index.php/news/items/18875",
        "evidence_types": ["webpage"],
        "sort_order": 80,
    },
]


def upgrade() -> None:
    table = op.create_table(
        "destination_region_stories",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("region_key", sa.String(length=128), nullable=False),
        sa.Column("story_type", sa.String(length=40), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("evidence_types", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "story_type LIKE 'destination_%'",
            name="ck_destination_region_stories_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "region_key",
            "story_type",
            "source_url",
            name="uq_destination_region_stories_source",
        ),
    )
    op.create_index(
        "ix_destination_region_stories_region_active_order",
        "destination_region_stories",
        ["region_key", "is_active", "sort_order"],
    )

    fetched_at = datetime(2026, 8, 8, tzinfo=timezone.utc)
    op.bulk_insert(
        table,
        [
            {
                **story,
                "fetched_at": fetched_at,
                "is_active": True,
            }
            for story in HANOI_REGION_STORIES
        ],
    )

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    stories_payload = [
        {
            "type": story["story_type"],
            "text": story["text"],
            "ref": story["source_url"],
            "evidenceTypes": story["evidence_types"],
            "fetchedAt": "2026-08-08T00:00:00Z",
        }
        for story in HANOI_REGION_STORIES
    ]
    serialized_stories = json.dumps(stories_payload, ensure_ascii=False)

    # URL imports retain their place observations and artifacts, but no longer
    # own destination-level content.
    bind.execute(
        sa.text(
            """
            UPDATE source_documents
            SET extracted_context = (extracted_context::jsonb - 'regionStory')::json
            WHERE extracted_context::jsonb ? 'regionStory'
            """
        )
    )

    # Repair the known legacy encoding in the restored dump before matching
    # existing Hanoi snapshots.
    bind.execute(
        sa.text(
            """
            UPDATE trip_chats
            SET destination = 'Hà Nội',
                current_plan = CASE
                    WHEN current_plan IS NULL THEN NULL
                    ELSE jsonb_set(
                        current_plan::jsonb,
                        '{destination}',
                        to_jsonb('Hà Nội'::text),
                        true
                    )::json
                END
            WHERE destination = 'H? N?i'
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE knowledge_graph_imports
            SET destination = 'Hà Nội'
            WHERE destination = 'H? N?i'
            """
        )
    )

    hanoi_condition = """
        lower(coalesce(destination, '')) IN ('hà nội', 'ha noi', 'hanoi')
        OR lower(coalesce(current_plan::jsonb->>'destination', ''))
            IN ('hà nội', 'ha noi', 'hanoi')
    """
    bind.execute(
        sa.text(
            f"""
            UPDATE trip_chats
            SET current_plan = jsonb_set(
                current_plan::jsonb,
                '{{regionStories}}',
                CAST(:stories AS jsonb),
                true
            )::json
            WHERE current_plan IS NOT NULL AND ({hanoi_condition})
            """
        ),
        {"stories": serialized_stories},
    )
    bind.execute(
        sa.text(
            """
            UPDATE trip_revisions AS revision
            SET plan_payload = jsonb_set(
                revision.plan_payload::jsonb,
                '{regionStories}',
                CAST(:stories AS jsonb),
                true
            )::json
            FROM trip_chats AS chat
            WHERE revision.chat_id = chat.id
              AND revision.plan_payload IS NOT NULL
              AND (
                  lower(coalesce(chat.destination, ''))
                      IN ('hà nội', 'ha noi', 'hanoi')
                  OR lower(coalesce(revision.plan_payload::jsonb->>'destination', ''))
                      IN ('hà nội', 'ha noi', 'hanoi', 'h? n?i')
              )
            """
        ),
        {"stories": serialized_stories},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_destination_region_stories_region_active_order",
        table_name="destination_region_stories",
    )
    op.drop_table("destination_region_stories")
