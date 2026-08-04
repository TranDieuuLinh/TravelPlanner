"""add public country travel groups and memberships

Revision ID: 20260801_0015
Revises: 20260731_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0015"
down_revision: str | None = "20260731_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_PHOTO_URL = (
    "https://images.unsplash.com/photo-1488646953014-85cb44e25828"
    "?auto=format&fit=crop&w=900&q=80"
)

# 193 UN member states plus the two UN observer states (Palestine and Vatican City).
COUNTRIES = [
    ("AF", "Afghanistan"),
    ("AL", "Albania"),
    ("DZ", "Algeria"),
    ("AD", "Andorra"),
    ("AO", "Angola"),
    ("AG", "Antigua và Barbuda"),
    ("AR", "Argentina"),
    ("AM", "Armenia"),
    ("AU", "Australia"),
    ("AT", "Áo"),
    ("AZ", "Azerbaijan"),
    ("BS", "Bahamas"),
    ("BH", "Bahrain"),
    ("BD", "Bangladesh"),
    ("BB", "Barbados"),
    ("BY", "Belarus"),
    ("BE", "Bỉ"),
    ("BZ", "Belize"),
    ("BJ", "Benin"),
    ("BT", "Bhutan"),
    ("BO", "Bolivia"),
    ("BA", "Bosnia và Herzegovina"),
    ("BW", "Botswana"),
    ("BR", "Brazil"),
    ("BN", "Brunei"),
    ("BG", "Bulgaria"),
    ("BF", "Burkina Faso"),
    ("BI", "Burundi"),
    ("CV", "Cape Verde"),
    ("KH", "Campuchia"),
    ("CM", "Cameroon"),
    ("CA", "Canada"),
    ("CF", "Cộng hòa Trung Phi"),
    ("TD", "Chad"),
    ("CL", "Chile"),
    ("CN", "Trung Quốc"),
    ("CO", "Colombia"),
    ("KM", "Comoros"),
    ("CG", "Congo - Brazzaville"),
    ("CD", "Congo - Kinshasa"),
    ("CR", "Costa Rica"),
    ("CI", "Côte d’Ivoire"),
    ("HR", "Croatia"),
    ("CU", "Cuba"),
    ("CY", "Síp"),
    ("CZ", "Séc"),
    ("DK", "Đan Mạch"),
    ("DJ", "Djibouti"),
    ("DM", "Dominica"),
    ("DO", "Cộng hòa Dominica"),
    ("EC", "Ecuador"),
    ("EG", "Ai Cập"),
    ("SV", "El Salvador"),
    ("GQ", "Guinea Xích Đạo"),
    ("ER", "Eritrea"),
    ("EE", "Estonia"),
    ("SZ", "Eswatini"),
    ("ET", "Ethiopia"),
    ("FJ", "Fiji"),
    ("FI", "Phần Lan"),
    ("FR", "Pháp"),
    ("GA", "Gabon"),
    ("GM", "Gambia"),
    ("GE", "Georgia"),
    ("DE", "Đức"),
    ("GH", "Ghana"),
    ("GR", "Hy Lạp"),
    ("GD", "Grenada"),
    ("GT", "Guatemala"),
    ("GN", "Guinea"),
    ("GW", "Guinea-Bissau"),
    ("GY", "Guyana"),
    ("HT", "Haiti"),
    ("HN", "Honduras"),
    ("HU", "Hungary"),
    ("IS", "Iceland"),
    ("IN", "Ấn Độ"),
    ("ID", "Indonesia"),
    ("IR", "Iran"),
    ("IQ", "Iraq"),
    ("IE", "Ireland"),
    ("IL", "Israel"),
    ("IT", "Italy"),
    ("JM", "Jamaica"),
    ("JP", "Nhật Bản"),
    ("JO", "Jordan"),
    ("KZ", "Kazakhstan"),
    ("KE", "Kenya"),
    ("KI", "Kiribati"),
    ("KP", "Triều Tiên"),
    ("KR", "Hàn Quốc"),
    ("KW", "Kuwait"),
    ("KG", "Kyrgyzstan"),
    ("LA", "Lào"),
    ("LV", "Latvia"),
    ("LB", "Li-băng"),
    ("LS", "Lesotho"),
    ("LR", "Liberia"),
    ("LY", "Libya"),
    ("LI", "Liechtenstein"),
    ("LT", "Litva"),
    ("LU", "Luxembourg"),
    ("MG", "Madagascar"),
    ("MW", "Malawi"),
    ("MY", "Malaysia"),
    ("MV", "Maldives"),
    ("ML", "Mali"),
    ("MT", "Malta"),
    ("MH", "Quần đảo Marshall"),
    ("MR", "Mauritania"),
    ("MU", "Mauritius"),
    ("MX", "Mexico"),
    ("FM", "Micronesia"),
    ("MD", "Moldova"),
    ("MC", "Monaco"),
    ("MN", "Mông Cổ"),
    ("ME", "Montenegro"),
    ("MA", "Ma-rốc"),
    ("MZ", "Mozambique"),
    ("MM", "Myanmar (Miến Điện)"),
    ("NA", "Namibia"),
    ("NR", "Nauru"),
    ("NP", "Nepal"),
    ("NL", "Hà Lan"),
    ("NZ", "New Zealand"),
    ("NI", "Nicaragua"),
    ("NE", "Niger"),
    ("NG", "Nigeria"),
    ("MK", "Bắc Macedonia"),
    ("NO", "Na Uy"),
    ("OM", "Oman"),
    ("PK", "Pakistan"),
    ("PW", "Palau"),
    ("PA", "Panama"),
    ("PG", "Papua New Guinea"),
    ("PY", "Paraguay"),
    ("PE", "Peru"),
    ("PH", "Philippines"),
    ("PL", "Ba Lan"),
    ("PT", "Bồ Đào Nha"),
    ("QA", "Qatar"),
    ("RO", "Romania"),
    ("RU", "Nga"),
    ("RW", "Rwanda"),
    ("KN", "St. Kitts và Nevis"),
    ("LC", "St. Lucia"),
    ("VC", "St. Vincent và Grenadines"),
    ("WS", "Samoa"),
    ("SM", "San Marino"),
    ("ST", "São Tomé và Príncipe"),
    ("SA", "Ả Rập Xê-út"),
    ("SN", "Senegal"),
    ("RS", "Serbia"),
    ("SC", "Seychelles"),
    ("SL", "Sierra Leone"),
    ("SG", "Singapore"),
    ("SK", "Slovakia"),
    ("SI", "Slovenia"),
    ("SB", "Quần đảo Solomon"),
    ("SO", "Somalia"),
    ("ZA", "Nam Phi"),
    ("SS", "Nam Sudan"),
    ("ES", "Tây Ban Nha"),
    ("LK", "Sri Lanka"),
    ("SD", "Sudan"),
    ("SR", "Suriname"),
    ("SE", "Thụy Điển"),
    ("CH", "Thụy Sĩ"),
    ("SY", "Syria"),
    ("TJ", "Tajikistan"),
    ("TZ", "Tanzania"),
    ("TH", "Thái Lan"),
    ("TL", "Timor-Leste"),
    ("TG", "Togo"),
    ("TO", "Tonga"),
    ("TT", "Trinidad và Tobago"),
    ("TN", "Tunisia"),
    ("TR", "Thổ Nhĩ Kỳ"),
    ("TM", "Turkmenistan"),
    ("TV", "Tuvalu"),
    ("UG", "Uganda"),
    ("UA", "Ukraina"),
    ("AE", "Các Tiểu Vương quốc Ả Rập Thống nhất"),
    ("GB", "Vương quốc Anh"),
    ("US", "Hoa Kỳ"),
    ("UY", "Uruguay"),
    ("UZ", "Uzbekistan"),
    ("VU", "Vanuatu"),
    ("VE", "Venezuela"),
    ("VN", "Việt Nam"),
    ("YE", "Yemen"),
    ("ZM", "Zambia"),
    ("ZW", "Zimbabwe"),
    ("PS", "Lãnh thổ Palestine"),
    ("VA", "Thành Vatican"),
]


def upgrade() -> None:
    op.create_table(
        "travel_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("country_name", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("photo_url", sa.String(length=1000), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False, server_default="public"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("country_code", name="uq_travel_groups_country_code"),
    )
    op.create_index("ix_travel_groups_country_code", "travel_groups", ["country_code"])
    op.create_index("ix_travel_groups_country_name", "travel_groups", ["country_name"])
    op.create_index("ix_travel_groups_visibility", "travel_groups", ["visibility"])

    groups = sa.table(
        "travel_groups",
        sa.column("country_code", sa.String),
        sa.column("country_name", sa.String),
        sa.column("name", sa.String),
        sa.column("photo_url", sa.String),
        sa.column("visibility", sa.String),
    )
    op.bulk_insert(
        groups,
        [
            {
                "country_code": code,
                "country_name": country_name,
                "name": f"Cộng đồng du lịch {country_name}",
                "photo_url": DEFAULT_PHOTO_URL,
                "visibility": "public",
            }
            for code, country_name in COUNTRIES
        ],
    )

    op.create_table(
        "travel_group_memberships",
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("travel_groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "group_id", "user_id", name="uq_travel_group_memberships_group_user"
        ),
    )
    op.create_index(
        "ix_travel_group_memberships_user_id", "travel_group_memberships", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_travel_group_memberships_user_id", table_name="travel_group_memberships")
    op.drop_table("travel_group_memberships")
    op.drop_index("ix_travel_groups_visibility", table_name="travel_groups")
    op.drop_index("ix_travel_groups_country_name", table_name="travel_groups")
    op.drop_index("ix_travel_groups_country_code", table_name="travel_groups")
    op.drop_table("travel_groups")
