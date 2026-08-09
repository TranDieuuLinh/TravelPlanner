"""Create curated Activity/Item nodes from more-node.yaml without graph edges."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select


APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.modules.knowledge_graph.model import (  # noqa: E402
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeProperty,
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.text import normalize_knowledge_text  # noqa: E402


SOURCE = "curation:crawl-for-res-dri-des/more-node.yaml:2026-08-09"
NOTE = "Human-curated taxonomy seed; no graph relationships created."


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def activity(
    entity_id: str,
    name: str,
    category: str,
    description: str,
    duration: int,
    slots: list[tuple[str, str]],
    aliases: list[tuple[str, str]] | None = None,
    **extra: object,
) -> dict[str, object]:
    properties: dict[str, object] = {
        "description": description,
        "activity_category": category,
        "typical_duration_minutes": duration,
        "best_time_slots": [{"start": start, "end": end} for start, end in slots],
        **extra,
    }
    return {
        "id": entity_id,
        "name": name,
        "type": "Activity",
        "aliases": aliases or [],
        "properties": properties,
    }


def item(
    entity_id: str,
    name: str,
    entity_type: str,
    item_category: str,
    description: str,
    meal_roles: list[str] | None = None,
    aliases: list[tuple[str, str]] | None = None,
    cuisine: str | None = None,
    **extra: object,
) -> dict[str, object]:
    properties: dict[str, object] = {
        "description": description,
        "item_category": item_category,
        **extra,
    }
    if meal_roles:
        properties["meal_roles"] = meal_roles
    if cuisine:
        properties["cuisine"] = cuisine
    return {
        "id": entity_id,
        "name": name,
        "type": entity_type,
        "aliases": aliases or [],
        "properties": properties,
    }


ACTIVITIES = [
    activity("activity_indoor_golf", "Chơi golf trong nhà", "sports", "Hoạt động chơi hoặc luyện tập golf tại cơ sở trong nhà, thường sử dụng phòng tập hoặc thiết bị mô phỏng.", 90, [("09:00", "12:00"), ("14:00", "21:00")], [("Golf trong nhà", "vi"), ("Indoor golf", "en")], indoor=True),
    activity("activity_children_play", "Vui chơi dành cho trẻ em", "family", "Hoạt động vui chơi phù hợp với trẻ em tại không gian có trò chơi hoặc tiện ích dành cho gia đình.", 120, [("09:00", "12:00"), ("15:00", "20:00")], [("Khu vui chơi cho trẻ con", "vi"), ("Khu vui chơi trẻ em", "vi")]),
    activity("activity_casino", "Chơi casino", "entertainment", "Hoạt động giải trí có đặt cược tại cơ sở được pháp luật cho phép; chỉ phù hợp với người đáp ứng điều kiện về độ tuổi và quy định vào cửa.", 120, [("19:00", "23:00")], [("Đánh bạc", "vi"), ("Casino", "en")], minimum_age=18, requires_legal_venue=True),
    activity("activity_swimming", "Đi bơi", "sports", "Hoạt động bơi lội tại hồ bơi, khu nghỉ dưỡng hoặc khu vực được phép và bảo đảm an toàn.", 60, [("06:00", "09:00"), ("16:00", "19:00")], [("Bơi lội", "vi")]),
    activity("activity_cultural_experience", "Trải nghiệm văn hóa", "culture", "Hoạt động tìm hiểu hoặc tham gia trực tiếp vào văn hóa, tập quán, nghề thủ công hay đời sống bản địa.", 120, [("09:00", "11:30"), ("14:00", "17:00")], [("Hoạt động văn hóa", "vi")]),
    activity("activity_billiards", "Chơi bida", "entertainment", "Hoạt động chơi bida hoặc bi-a tại câu lạc bộ và cơ sở giải trí phù hợp.", 90, [("14:00", "23:00")], [("Chơi bi-a", "vi"), ("Bida", "vi")], indoor=True),
    activity("activity_souvenir_shopping", "Mua đồ lưu niệm", "shopping", "Hoạt động tìm và mua quà lưu niệm hoặc sản phẩm đặc trưng của điểm đến.", 60, [("09:00", "12:00"), ("14:00", "20:00")], [("Mua quà lưu niệm", "vi"), ("Souvenir shopping", "en")]),
    activity("activity_watch_art_performance", "Xem biểu diễn nghệ thuật", "entertainment", "Hoạt động xem chương trình sân khấu, âm nhạc, múa hoặc loại hình nghệ thuật biểu diễn khác.", 120, [("10:00", "12:00"), ("19:00", "22:00")], [("Xem biểu diễn", "vi"), ("Xem show nghệ thuật", "vi")]),
    activity("activity_cosplay", "Cosplay", "entertainment", "Hoạt động hóa trang thành nhân vật, thường kết hợp giao lưu, sự kiện hoặc chụp ảnh.", 120, [("09:00", "12:00"), ("14:00", "18:00")], [("Hóa trang nhân vật", "vi")]),
    activity("activity_studio_photography", "Chụp ảnh studio", "creative", "Hoạt động chụp ảnh trong studio có bối cảnh, ánh sáng hoặc trang phục được chuẩn bị.", 90, [("09:00", "12:00"), ("14:00", "19:00")], [("Chụp hình studio", "vi")], indoor=True),
    activity("activity_fair_attendance", "Tham gia hội chợ", "event", "Hoạt động tham quan, mua sắm hoặc trải nghiệm tại hội chợ và sự kiện diễn ra trong thời gian giới hạn.", 120, [("09:00", "12:00"), ("17:00", "21:00")], [("Đi hội chợ", "vi")], schedule_dependent=True),
    activity("activity_camping", "Cắm trại", "outdoor", "Hoạt động lưu lại ngoài trời tại khu vực cho phép, có thể gồm dựng lều, nghỉ ngơi và sinh hoạt dã ngoại.", 360, [("08:00", "18:00")], [("Camping", "en")], weather_dependent=True),
    activity("activity_horse_riding", "Cưỡi ngựa", "outdoor", "Hoạt động cưỡi ngựa tại cơ sở hoặc khu vực có hướng dẫn và điều kiện an toàn phù hợp.", 60, [("07:00", "10:00"), ("15:30", "18:00")], [("Horse riding", "en")], weather_dependent=True),
]


ACTIVITIES += [
    # Dining and nightlife activities useful for filling itinerary gaps.
    activity("activity_breakfast", "Ăn sáng", "dining", "Dùng bữa sáng tại nhà hàng, quán ăn hoặc địa điểm phục vụ món buổi sáng.", 45, [("06:00", "10:00")], [("Breakfast", "en")]),
    activity("activity_lunch", "Ăn trưa", "dining", "Dùng bữa trưa tại nhà hàng hoặc quán ăn phù hợp với lịch trình trong ngày.", 60, [("11:00", "14:00")], [("Lunch", "en")]),
    activity("activity_dinner", "Ăn tối", "dining", "Dùng bữa tối tại nhà hàng hoặc quán ăn, có thể kết hợp trải nghiệm ẩm thực địa phương.", 90, [("18:00", "21:30")], [("Dinner", "en")]),
    activity("activity_local_food", "Thưởng thức ẩm thực địa phương", "dining", "Khám phá các món ăn tiêu biểu gắn với địa phương hoặc vùng miền của điểm đến.", 90, [("07:00", "10:00"), ("11:00", "14:00"), ("18:00", "21:00")], [("Ăn đặc sản địa phương", "vi"), ("Local food experience", "en")]),
    activity("activity_street_food", "Khám phá ẩm thực đường phố", "dining", "Thử nhiều món ăn và đồ uống tại các quán nhỏ, khu phố hoặc chợ ẩm thực đường phố.", 120, [("16:00", "22:00")], [("Đi ăn phố", "vi"), ("Street food tour", "en")]),
    activity("activity_vegetarian_meal", "Ăn chay", "dining", "Dùng bữa với thực đơn chay tại nhà hàng hoặc quán ăn có lựa chọn phù hợp.", 60, [("11:00", "14:00"), ("18:00", "21:00")], [("Vegetarian meal", "en")]),
    activity("activity_buffet", "Ăn buffet", "dining", "Dùng bữa theo hình thức tự chọn nhiều món trong một khoảng thời gian tại nhà hàng.", 120, [("11:00", "14:00"), ("18:00", "21:30")], [("Buffet", "en")]),
    activity("activity_hot_pot", "Ăn lẩu", "dining", "Dùng bữa với món lẩu nóng và các nguyên liệu được nhúng chín tại bàn, thường phù hợp đi theo nhóm.", 120, [("11:00", "14:00"), ("18:00", "22:00")], [("Đi ăn lẩu", "vi"), ("Hot pot", "en")]),
    activity("activity_barbecue", "Ăn đồ nướng", "dining", "Dùng bữa với các món nướng tại bàn hoặc được nhà hàng chế biến, thường phù hợp đi theo nhóm.", 120, [("11:00", "14:00"), ("18:00", "22:00")], [("Đi ăn nướng", "vi"), ("Barbecue meal", "en")]),
    activity("activity_seafood_meal", "Ăn hải sản", "dining", "Dùng bữa tập trung vào các món hải sản tại nhà hàng hoặc khu ẩm thực phù hợp.", 90, [("11:00", "14:00"), ("18:00", "21:30")], [("Seafood meal", "en")]),
    activity("activity_snacking", "Ăn đồ ăn vặt", "dining", "Thưởng thức món ăn nhẹ giữa các bữa chính hoặc trong khi khám phá điểm đến.", 45, [("09:00", "11:00"), ("14:00", "18:00"), ("20:00", "23:00")], [("Ăn vặt", "vi"), ("Snacking", "en")]),
    activity("activity_late_night_food", "Ăn đêm", "dining", "Dùng bữa muộn hoặc thưởng thức món ăn đêm sau các hoạt động buổi tối.", 60, [("21:00", "23:59")], [("Late-night food", "en")]),
    activity("activity_drinking_gathering", "Đi nhậu", "nightlife", "Gặp gỡ và dùng đồ uống cùng các món nhắm tại quán ăn, quán bia hoặc cơ sở phù hợp.", 120, [("18:00", "23:00")], [("Nhậu", "vi"), ("Drinking gathering", "en")], minimum_age=18),
    activity("activity_go_bar", "Đi bar", "nightlife", "Trải nghiệm đồ uống và không gian giải trí buổi tối tại quán bar phù hợp.", 120, [("19:00", "23:59")], [("Bar hopping", "en")], minimum_age=18),
    activity("activity_go_pub", "Đi pub", "nightlife", "Thư giãn, trò chuyện và dùng đồ uống tại pub trong khung giờ buổi tối.", 120, [("18:00", "23:59")], [("Pub", "en")], minimum_age=18),
    activity("activity_rooftop_bar", "Đi rooftop bar", "nightlife", "Dùng đồ uống tại quán bar trên cao, thường kết hợp ngắm hoàng hôn hoặc cảnh thành phố về đêm.", 90, [("17:00", "23:00")], [("Bar sân thượng", "vi"), ("Rooftop bar", "en")], minimum_age=18, weather_dependent=True),
    activity("activity_nightclub", "Đi câu lạc bộ đêm", "nightlife", "Trải nghiệm âm nhạc, khiêu vũ và không khí giải trí tại câu lạc bộ đêm.", 180, [("21:00", "23:59")], [("Đi club", "vi"), ("Nightclub", "en")], minimum_age=18),
    activity("activity_drink_cocktail", "Uống cocktail", "nightlife", "Thưởng thức cocktail tại bar, lounge hoặc nhà hàng có dịch vụ pha chế.", 90, [("17:00", "23:00")], [("Thưởng thức cocktail", "vi")], minimum_age=18),
    activity("activity_drink_beer", "Uống bia", "nightlife", "Thưởng thức bia tại nhà hàng, quán bia, pub hoặc cơ sở phục vụ đồ uống phù hợp.", 90, [("17:00", "23:00")], [("Thưởng thức bia", "vi")], minimum_age=18),
    activity("activity_drink_draft_beer", "Uống bia hơi", "nightlife", "Trải nghiệm bia hơi và các món ăn kèm tại quán bia địa phương.", 90, [("17:00", "22:30")], [("Nhậu bia hơi", "vi"), ("Fresh beer", "en")], minimum_age=18),
    activity("activity_live_music", "Nghe nhạc sống", "nightlife", "Xem và nghe nghệ sĩ biểu diễn trực tiếp tại quán, sân khấu hoặc không gian âm nhạc.", 120, [("19:00", "23:00")], [("Live music", "en")], schedule_dependent=True),
    activity("activity_night_market", "Dạo chợ đêm", "nightlife", "Khám phá chợ hoạt động vào buổi tối để ăn uống, mua sắm và quan sát đời sống địa phương.", 120, [("18:00", "23:00")], [("Đi chợ đêm", "vi"), ("Night market", "en")]),
    activity("activity_night_view", "Ngắm thành phố về đêm", "nightlife", "Ngắm cảnh đô thị và ánh sáng thành phố từ tuyến phố, bờ hồ, đài quan sát hoặc điểm nhìn phù hợp.", 90, [("18:30", "22:30")], [("Ngắm cảnh đêm", "vi"), ("City night view", "en")]),
    # Culture and local discovery.
    activity("activity_museum_visit", "Tham quan bảo tàng", "culture", "Khám phá bộ sưu tập và nội dung trưng bày tại bảo tàng.", 120, [("09:00", "11:30"), ("14:00", "17:00")], [("Đi bảo tàng", "vi"), ("Museum visit", "en")], schedule_dependent=True),
    activity("activity_historic_site_visit", "Tham quan di tích lịch sử", "culture", "Tìm hiểu lịch sử và giá trị của di tích, công trình hoặc địa điểm có ý nghĩa lịch sử.", 90, [("08:00", "11:00"), ("14:00", "17:00")], [("Thăm di tích", "vi")]),
    activity("activity_religious_site_visit", "Tham quan đền chùa", "culture", "Tham quan đền, chùa hoặc cơ sở tín ngưỡng với trang phục và cách ứng xử phù hợp.", 60, [("07:00", "11:00"), ("14:00", "17:00")], [("Đi lễ đền chùa", "vi"), ("Temple visit", "en")]),
    activity("activity_exhibition_visit", "Xem triển lãm", "culture", "Tham quan triển lãm nghệ thuật, lịch sử, khoa học hoặc nội dung chuyên đề.", 90, [("09:00", "12:00"), ("14:00", "18:00")], [("Đi triển lãm", "vi"), ("Exhibition visit", "en")], schedule_dependent=True),
    activity("activity_craft_workshop", "Tham gia workshop thủ công", "creative", "Học và tự thực hành một kỹ thuật thủ công dưới sự hướng dẫn tại xưởng hoặc không gian trải nghiệm.", 120, [("09:00", "12:00"), ("14:00", "17:00")], [("Workshop thủ công", "vi"), ("Craft workshop", "en")], schedule_dependent=True),
    activity("activity_craft_village_visit", "Tham quan làng nghề", "culture", "Khám phá làng nghề, quy trình sản xuất và sản phẩm thủ công đặc trưng của địa phương.", 180, [("08:00", "12:00"), ("13:30", "17:00")], [("Đi làng nghề", "vi")]),
    activity("activity_walking_tour", "Tham gia tour đi bộ", "sightseeing", "Khám phá một khu vực theo tuyến đi bộ có chủ đề hoặc người hướng dẫn.", 150, [("08:00", "11:00"), ("16:00", "19:00")], [("Walking tour", "en")], schedule_dependent=True),
    activity("activity_food_tour", "Tham gia tour ẩm thực", "dining", "Khám phá nhiều món ăn và địa điểm ẩm thực theo một tuyến có chủ đề hoặc người hướng dẫn.", 180, [("08:00", "11:00"), ("17:00", "21:00")], [("Food tour", "en")], schedule_dependent=True),
    # Outdoor, scenic, and nature activities.
    activity("activity_sunrise", "Ngắm bình minh", "outdoor", "Đến điểm nhìn phù hợp để ngắm ánh sáng và cảnh quan lúc mặt trời mọc.", 60, [("05:00", "07:00")], [("Săn bình minh", "vi"), ("Sunrise viewing", "en")], weather_dependent=True),
    activity("activity_sunset", "Ngắm hoàng hôn", "outdoor", "Đến điểm nhìn phù hợp để ngắm cảnh quan và ánh sáng vào cuối ngày.", 60, [("16:30", "18:30")], [("Săn hoàng hôn", "vi"), ("Sunset viewing", "en")], weather_dependent=True),
    activity("activity_picnic", "Đi picnic", "outdoor", "Nghỉ ngơi và ăn uống nhẹ ngoài trời tại công viên hoặc khu vực được phép.", 180, [("08:00", "11:30"), ("15:00", "18:00")], [("Dã ngoại", "vi"), ("Picnic", "en")], weather_dependent=True),
    activity("activity_hiking", "Đi bộ đường dài", "outdoor", "Đi bộ trên tuyến thiên nhiên hoặc địa hình có độ dài và độ khó vừa phải.", 240, [("06:00", "11:00"), ("14:00", "18:00")], [("Hiking", "en")], weather_dependent=True),
    activity("activity_trekking", "Trekking", "adventure", "Đi bộ khám phá địa hình tự nhiên trên tuyến dài hoặc khó, cần chuẩn bị thể lực và trang thiết bị phù hợp.", 360, [("06:00", "16:00")], [("Đi trekking", "vi")], weather_dependent=True),
    activity("activity_cycling", "Đạp xe", "outdoor", "Khám phá khu vực bằng xe đạp trên tuyến đường phù hợp và an toàn.", 120, [("06:00", "09:00"), ("16:00", "19:00")], [("Cycling", "en")], weather_dependent=True),
    activity("activity_kayaking", "Chèo kayak", "adventure", "Chèo thuyền kayak trên vùng nước được phép, với thiết bị an toàn và hướng dẫn khi cần.", 120, [("07:00", "11:00"), ("15:00", "18:00")], [("Kayaking", "en")], weather_dependent=True),
    activity("activity_boat_ride", "Đi thuyền", "sightseeing", "Tham quan cảnh quan bằng thuyền trên sông, hồ, vịnh hoặc vùng nước phù hợp.", 120, [("08:00", "11:00"), ("14:00", "17:30")], [("Boat ride", "en")], weather_dependent=True),
    activity("activity_fishing", "Câu cá", "outdoor", "Câu cá tại hồ, sông hoặc khu dịch vụ cho phép, tuân thủ quy định địa phương.", 180, [("06:00", "10:00"), ("15:00", "18:30")], [("Fishing", "en")], weather_dependent=True),
    activity("activity_scenic_view", "Ngắm cảnh", "sightseeing", "Dừng chân tại điểm nhìn hoặc khu vực có cảnh quan đẹp để quan sát và nghỉ ngơi.", 60, [("07:00", "11:00"), ("15:00", "18:30")], [("Scenic viewing", "en")], weather_dependent=True),
    activity("activity_park_visit", "Tham quan công viên", "outdoor", "Đi dạo, thư giãn hoặc tham gia hoạt động nhẹ tại công viên.", 90, [("06:00", "10:00"), ("15:30", "19:00")], [("Đi công viên", "vi"), ("Park visit", "en")], weather_dependent=True),
    activity("activity_garden_visit", "Tham quan vườn hoa", "outdoor", "Tham quan và chụp ảnh tại vườn hoa hoặc không gian cảnh quan theo mùa.", 90, [("07:00", "11:00"), ("15:00", "18:00")], [("Đi vườn hoa", "vi"), ("Flower garden visit", "en")], weather_dependent=True),
    activity("activity_outdoor_photography", "Chụp ảnh ngoài trời", "creative", "Chụp ảnh tại cảnh quan, phố, công viên hoặc địa điểm ngoài trời phù hợp.", 90, [("06:30", "09:30"), ("15:30", "18:30")], [("Chụp hình ngoài trời", "vi")], weather_dependent=True),
    activity("activity_beach_visit", "Đi biển", "outdoor", "Thư giãn và tham gia hoạt động tại bãi biển an toàn, phù hợp với điều kiện thời tiết.", 180, [("06:00", "10:00"), ("15:00", "18:30")], [("Tắm biển", "vi"), ("Beach visit", "en")], weather_dependent=True),
    # Family entertainment and indoor gap-fillers.
    activity("activity_zoo_visit", "Tham quan sở thú", "family", "Tham quan khu nuôi dưỡng và giới thiệu động vật tại sở thú hoặc vườn thú.", 180, [("08:00", "11:00"), ("14:00", "17:00")], [("Đi sở thú", "vi"), ("Zoo visit", "en")]),
    activity("activity_aquarium_visit", "Tham quan thủy cung", "family", "Khám phá các khu trưng bày sinh vật thủy sinh trong thủy cung.", 120, [("09:00", "12:00"), ("14:00", "19:00")], [("Đi thủy cung", "vi"), ("Aquarium visit", "en")], indoor=True),
    activity("activity_amusement_park", "Đi công viên giải trí", "family", "Tham gia trò chơi và hoạt động giải trí tại công viên chủ đề hoặc khu vui chơi lớn.", 240, [("09:00", "18:00")], [("Công viên chủ đề", "vi"), ("Amusement park", "en")]),
    activity("activity_water_park", "Đi công viên nước", "family", "Tham gia trò chơi dưới nước tại công viên nước với yêu cầu an toàn phù hợp.", 240, [("09:00", "17:00")], [("Water park", "en")], weather_dependent=True),
    activity("activity_arcade", "Chơi game arcade", "entertainment", "Chơi các trò điện tử và trò kỹ năng tại khu arcade hoặc trung tâm giải trí.", 90, [("10:00", "22:00")], [("Khu trò chơi điện tử", "vi"), ("Arcade", "en")], indoor=True),
    activity("activity_escape_room", "Chơi escape room", "entertainment", "Giải câu đố theo nhóm trong phòng chơi có chủ đề và thời lượng giới hạn.", 90, [("10:00", "22:00")], [("Phòng thoát hiểm", "vi"), ("Escape room", "en")], indoor=True, schedule_dependent=True),
    activity("activity_bowling", "Chơi bowling", "sports", "Chơi bowling tại trung tâm giải trí hoặc câu lạc bộ có làn chơi phù hợp.", 90, [("10:00", "22:00")], [("Bowling", "en")], indoor=True),
    activity("activity_cinema", "Xem phim", "entertainment", "Xem phim tại rạp theo suất chiếu được công bố.", 150, [("10:00", "23:00")], [("Đi xem phim", "vi"), ("Cinema", "en")], indoor=True, schedule_dependent=True),
    # Wellness and adventure.
    activity("activity_massage", "Massage", "wellness", "Sử dụng dịch vụ massage thư giãn hoặc phục hồi tại cơ sở phù hợp.", 90, [("10:00", "21:00")], [("Mát-xa", "vi")], indoor=True),
    activity("activity_hot_spring", "Tắm khoáng nóng", "wellness", "Ngâm mình và thư giãn tại khu khoáng nóng hoặc cơ sở tắm khoáng.", 150, [("09:00", "12:00"), ("15:00", "20:00")], [("Tắm suối khoáng", "vi"), ("Hot spring", "en")]),
    activity("activity_yoga", "Tập yoga", "wellness", "Tham gia buổi tập yoga tại studio hoặc không gian phù hợp.", 60, [("06:00", "09:00"), ("17:00", "20:00")], [("Yoga", "en")], schedule_dependent=True),
    activity("activity_meditation", "Thiền", "wellness", "Thực hành thiền trong không gian yên tĩnh hoặc theo buổi hướng dẫn.", 45, [("06:00", "09:00"), ("17:00", "20:00")], [("Meditation", "en")]),
    activity("activity_zipline", "Chơi zipline", "adventure", "Di chuyển trên dây trượt tại khu phiêu lưu có thiết bị bảo hộ và hướng dẫn an toàn.", 90, [("08:00", "11:00"), ("14:00", "17:00")], [("Zipline", "en")], weather_dependent=True),
    activity("activity_rock_climbing", "Leo núi đá", "adventure", "Leo trên vách đá tự nhiên hoặc khu leo núi chuyên dụng với thiết bị và hướng dẫn phù hợp.", 180, [("07:00", "11:00"), ("14:00", "18:00")], [("Rock climbing", "en")], weather_dependent=True),
    activity("activity_paragliding", "Dù lượn", "adventure", "Bay dù lượn tại khu vực được phép với đơn vị vận hành và điều kiện thời tiết phù hợp.", 120, [("08:00", "11:00"), ("14:00", "17:00")], [("Paragliding", "en")], weather_dependent=True, schedule_dependent=True),
    activity("activity_snorkeling", "Lặn ngắm san hô", "adventure", "Bơi với ống thở để quan sát sinh vật biển tại vùng nước được phép và an toàn.", 150, [("07:00", "11:00"), ("14:00", "17:00")], [("Snorkeling", "en")], weather_dependent=True),
    activity("activity_surfing", "Lướt sóng", "adventure", "Lướt sóng tại bãi biển phù hợp với kỹ năng, thiết bị và điều kiện thời tiết.", 120, [("06:00", "10:00"), ("15:00", "18:00")], [("Surfing", "en")], weather_dependent=True),
    # Destination transport experiences.
    activity("activity_cable_car", "Đi cáp treo", "sightseeing", "Di chuyển bằng cáp treo để tiếp cận điểm tham quan hoặc ngắm cảnh từ trên cao.", 60, [("08:00", "11:30"), ("14:00", "17:30")], [("Cable car ride", "en")], weather_dependent=True, schedule_dependent=True),
    activity("activity_cyclo_ride", "Đi xích lô", "sightseeing", "Khám phá khu phố bằng xích lô trên tuyến phù hợp và tuân thủ quy định giao thông.", 60, [("08:00", "11:00"), ("16:00", "19:00")], [("Cyclo ride", "en")], weather_dependent=True),
    activity("activity_scenic_train", "Đi tàu ngắm cảnh", "sightseeing", "Trải nghiệm tuyến tàu có giá trị ngắm cảnh hoặc khám phá địa phương.", 180, [("06:00", "18:00")], [("Scenic train ride", "en")], schedule_dependent=True),
]


DRINK_ITEMS = [
    item("drink_item_milk_tea", "Trà sữa", "DrinkItem", "milk_tea", "Đồ uống pha từ trà và sữa, có thể dùng kèm trân châu hoặc các loại topping.", ["snack"], [("Milk tea", "en"), ("Bubble tea", "en")], beverage_category="non_alcoholic"),
    item("drink_item_cocktail", "Cocktail", "DrinkItem", "cocktail", "Đồ uống pha chế từ nhiều thành phần, thường có cồn và được phục vụ tại bar hoặc nhà hàng.", ["drink"], [("Cocktails", "en")], beverage_category="alcoholic", minimum_age=18),
    item("drink_item_smoothie", "Sinh tố", "DrinkItem", "smoothie", "Đồ uống xay từ trái cây hoặc nguyên liệu thực vật, thường dùng lạnh.", ["snack"], [("Smoothie", "en")], beverage_category="non_alcoholic"),
    item("drink_item_coconut_water", "Nước dừa", "DrinkItem", "coconut_water", "Đồ uống từ nước quả dừa, thường dùng tươi hoặc ướp lạnh.", ["drink"], [("Coconut water", "en")], beverage_category="non_alcoholic"),
    item("drink_item_fruit_juice", "Nước trái cây", "DrinkItem", "fruit_juice", "Đồ uống làm từ nước ép trái cây, có thể dùng nguyên chất hoặc pha chế.", ["drink"], [("Nước ép trái cây", "vi"), ("Fruit juice", "en")], beverage_category="non_alcoholic"),
]


DRINK_ITEMS += [
    item("drink_item_beer", "Bia", "DrinkItem", "beer", "Đồ uống lên men có cồn từ ngũ cốc, được phục vụ với nhiều phong cách và nồng độ khác nhau.", ["drink"], [("Beer", "en")], beverage_category="alcoholic", minimum_age=18),
    item("drink_item_draft_beer", "Bia hơi", "DrinkItem", "draft_beer", "Bia tươi phổ biến tại Việt Nam, thường được phục vụ trong ngày tại quán bia và dùng cùng món nhắm.", ["drink"], [("Bia tươi", "vi"), ("Fresh beer", "en")], "Vietnamese", beverage_category="alcoholic", minimum_age=18),
    item("drink_item_wine", "Rượu vang", "DrinkItem", "wine", "Đồ uống có cồn làm từ nho hoặc trái cây, thường được dùng kèm bữa ăn.", ["drink"], [("Wine", "en")], beverage_category="alcoholic", minimum_age=18),
    item("drink_item_spirits", "Rượu mạnh", "DrinkItem", "spirits", "Nhóm đồ uống chưng cất có nồng độ cồn cao, thường dùng nguyên chất hoặc để pha chế.", ["drink"], [("Spirits", "en")], beverage_category="alcoholic", minimum_age=18),
    item("drink_item_mocktail", "Mocktail", "DrinkItem", "mocktail", "Đồ uống pha chế không cồn, sử dụng kỹ thuật và cách trình bày tương tự cocktail.", ["drink"], [("Cocktail không cồn", "vi")], beverage_category="non_alcoholic"),
]


FOOD_ITEMS = [
    item("food_item_sweet_soup", "Chè", "FoodItem", "dessert", "Món tráng miệng ngọt của Việt Nam với nhiều biến thể từ đậu, hạt, thạch, trái cây hoặc nước cốt dừa.", ["dessert", "snack"], [("Vietnamese sweet soup", "en")], "Vietnamese"),
    item("food_item_sweet_pastry", "Bánh ngọt", "FoodItem", "sweet_pastry", "Nhóm bánh có vị ngọt, thường dùng làm món tráng miệng hoặc bữa phụ.", ["dessert", "snack"]),
    item("food_item_savory_pastry", "Bánh mặn", "FoodItem", "savory_pastry", "Nhóm bánh có nhân hoặc gia vị mặn, thường dùng làm bữa phụ hoặc món ăn nhẹ.", ["snack"]),
    item("food_item_ice_cream", "Kem", "FoodItem", "frozen_dessert", "Món tráng miệng đông lạnh có nhiều hương vị và cách phục vụ.", ["dessert", "snack"], [("Ice cream", "en")]),
    item("food_item_banh_xeo", "Bánh xèo", "FoodItem", "savory_pancake", "Bánh mặn chiên giòn từ bột gạo, thường có nhân thịt, tôm và giá, ăn kèm rau cùng nước chấm.", ["main_meal", "snack"], cuisine="Vietnamese"),
    item("food_item_banh_mi", "Bánh mì", "FoodItem", "sandwich", "Món bánh mì Việt Nam, có thể ăn không hoặc kẹp nhiều loại nhân mặn và rau.", ["main_meal", "snack"], [("Bánh mỳ", "vi"), ("Vietnamese banh mi", "en")], "Vietnamese"),
    item("food_item_cheese_stick", "Phô mai que", "FoodItem", "fried_snack", "Món ăn nhẹ từ phô mai bọc bột và chiên, thường dùng nóng.", ["snack"], [("Cheese stick", "en")]),
    item("food_item_spring_roll", "Chả giò", "FoodItem", "fried_roll", "Cuốn nhân mặn được bọc bằng bánh tráng hoặc vỏ mỏng rồi chiên giòn.", ["main_meal", "snack"], [("Nem rán", "vi"), ("Fried spring roll", "en")], "Vietnamese"),
    item("food_item_rice_paper", "Bánh tráng", "FoodItem", "rice_paper_dish", "Nhóm món ăn hoặc món ăn vặt chế biến từ bánh tráng, với cách trộn, cuốn hoặc nướng khác nhau.", ["snack"], cuisine="Vietnamese"),
    item("food_item_shrimp_cake", "Bánh tôm", "FoodItem", "fried_cake", "Món bánh chiên có tôm, thường ăn kèm rau sống và nước chấm.", ["main_meal", "snack"], [("Shrimp cake", "en")], "Vietnamese"),
    item("food_item_nem_nuong", "Nem nướng", "FoodItem", "grilled_meat", "Món thịt xay tẩm gia vị và nướng, thường ăn kèm rau, bánh tráng và nước chấm.", ["main_meal", "snack"], cuisine="Vietnamese"),
    item("food_item_nem_chua", "Nem chua", "FoodItem", "fermented_meat", "Món thịt lên men có vị chua nhẹ, thường dùng như món ăn chơi hoặc món nhắm.", ["snack"], cuisine="Vietnamese"),
    item("food_item_fried_nem_chua", "Nem chua rán", "FoodItem", "fried_snack", "Món nem chiên hoặc rán dùng nóng, phổ biến như một món ăn vặt.", ["snack"], cuisine="Vietnamese"),
    item("food_item_banh_goi", "Bánh gối", "FoodItem", "fried_pastry", "Bánh vỏ bột gấp hình bán nguyệt, có nhân mặn và được chiên giòn.", ["snack"], [("Pillow cake", "en")], "Vietnamese"),
    item("food_item_dried_beef_salad", "Nộm bò khô", "FoodItem", "salad", "Món nộm kết hợp bò khô, rau củ, rau thơm và nước trộn chua ngọt.", ["snack", "main_meal"], cuisine="Vietnamese"),
    item("food_item_bun_bo", "Bún bò", "FoodItem", "noodle_soup", "Món bún dùng với thịt bò và nước dùng hoặc nước trộn, tùy phong cách vùng miền.", ["main_meal"], cuisine="Vietnamese"),
    item("food_item_bun_cha", "Bún chả", "FoodItem", "noodle_dish", "Món bún Hà Nội ăn cùng chả thịt nướng, nước chấm và rau sống.", ["main_meal"], cuisine="Vietnamese"),
    item("food_item_banh_cuon", "Bánh cuốn", "FoodItem", "steamed_rice_roll", "Bánh làm từ lớp bột gạo hấp mỏng, thường cuốn nhân và ăn với nước chấm.", ["main_meal", "snack"], cuisine="Vietnamese"),
    item("food_item_banh_canh", "Bánh canh", "FoodItem", "noodle_soup", "Món sợi dày làm từ bột gạo, bột mì hoặc bột lọc, dùng cùng nước dùng.", ["main_meal"], cuisine="Vietnamese"),
    item("food_item_banh_da", "Bánh đa", "FoodItem", "noodle_dish", "Nhóm món sử dụng sợi bánh đa, thường được phục vụ dạng nước hoặc trộn.", ["main_meal"], cuisine="Vietnamese"),
    item("food_item_mi_quang", "Mì Quảng", "FoodItem", "noodle_dish", "Món mì miền Trung với sợi mì, lượng nước dùng vừa phải, rau sống và nhiều loại nhân.", ["main_meal"], cuisine="Vietnamese"),
    item("food_item_hot_pot", "Lẩu", "FoodItem", "hot_pot", "Hình thức dùng bữa với nồi nước dùng nóng và các nguyên liệu được nhúng chín tại bàn.", ["main_meal"], [("Hot pot", "en")]),
    item("food_item_grilled_food", "Đồ nướng", "FoodItem", "barbecue", "Nhóm món được chế biến bằng cách nướng trên than, bếp hoặc vỉ, thường phù hợp dùng theo nhóm.", ["main_meal"], [("Món nướng", "vi"), ("Barbecue", "en")]),
    item("food_item_be_thui", "Bê thui", "FoodItem", "beef_dish", "Món thịt bê được thui hoặc quay chín, thái lát và thường ăn cùng rau cùng nước chấm.", ["main_meal"], cuisine="Vietnamese"),
    item("food_item_bo_to", "Bò tơ", "FoodItem", "beef_dish", "Nhóm món chế biến từ thịt bò non, có thể nướng, hấp, cuốn hoặc dùng trong lẩu.", ["main_meal"], cuisine="Vietnamese"),
    item("food_item_pizza", "Pizza", "FoodItem", "pizza", "Bánh nướng đế phẳng phủ sốt, phô mai và nhiều loại nguyên liệu khác nhau.", ["main_meal", "snack"], cuisine="Italian"),
    item("food_item_seafood", "Hải sản", "FoodItem", "seafood", "Nhóm món chế biến từ cá, tôm, cua, mực, sò và các loại thực phẩm từ biển khác.", ["main_meal"]),
    item("food_item_wonton_noodles", "Mì vằn thắn", "FoodItem", "noodle_soup", "Món mì dùng với vằn thắn, nước dùng và các loại thịt hoặc rau ăn kèm.", ["main_meal"], [("Mì hoành thánh", "vi")], "Chinese"),
    item("food_item_mushroom", "Nấm", "FoodItem", "mushroom_dish", "Nhóm món lấy nấm làm nguyên liệu chính, có thể dùng cho món chay hoặc món mặn.", ["main_meal"]),
    item("food_item_snail", "Ốc", "FoodItem", "shellfish", "Nhóm món chế biến từ ốc với nhiều phương pháp như luộc, hấp, xào hoặc nướng.", ["main_meal", "snack"], cuisine="Vietnamese"),
    item("food_item_sticky_rice", "Xôi", "FoodItem", "sticky_rice", "Món gạo nếp đồ chín, có thể dùng với nguyên liệu mặn hoặc ngọt.", ["main_meal", "snack"], cuisine="Vietnamese"),
    item("food_item_steamed_bun", "Bánh bao", "FoodItem", "steamed_bun", "Bánh bột hấp có thể có nhân mặn hoặc ngọt, phù hợp cho bữa nhanh hay bữa phụ.", ["main_meal", "snack"], cuisine="Asian"),
    item("food_item_banh_duc", "Bánh đúc", "FoodItem", "rice_cake", "Bánh truyền thống làm từ bột gạo, có biến thể mặn và ngọt.", ["main_meal", "snack"], cuisine="Vietnamese"),
    item("food_item_banh_gio", "Bánh giò", "FoodItem", "steamed_rice_cake", "Bánh bột gạo có nhân thịt, được gói lá và hấp chín.", ["main_meal", "snack"], cuisine="Vietnamese"),
    item("food_item_banh_khuc", "Bánh khúc", "FoodItem", "sticky_rice_cake", "Bánh từ gạo nếp, bột nếp và rau khúc, thường có nhân đậu xanh cùng thịt.", ["main_meal", "snack"], cuisine="Vietnamese"),
]


FOOD_ITEMS += [
    item("food_item_drinking_snacks", "Món nhắm", "FoodItem", "drinking_snack", "Nhóm món ăn dùng kèm bia, rượu hoặc đồ uống trong các buổi gặp gỡ.", ["snack"], [("Đồ nhắm", "vi")]),
    item("food_item_vegetarian_food", "Món chay", "FoodItem", "vegetarian_dish", "Nhóm món không sử dụng thịt hoặc hải sản, với thành phần cụ thể tùy món và cơ sở phục vụ.", ["main_meal"], [("Đồ ăn chay", "vi"), ("Vegetarian food", "en")], dietary_tags=["vegetarian"]),
]


PRODUCT_ITEMS = [
    item("product_item_souvenir", "Đồ lưu niệm", "ProductItem", "souvenir", "Sản phẩm được mua để lưu giữ kỷ niệm hoặc làm quà, thường gắn với văn hóa và hình ảnh của điểm đến.", aliases=[("Quà lưu niệm", "vi"), ("Souvenir", "en")], product_category="souvenir"),
    item("product_item_handicraft", "Đồ thủ công mỹ nghệ", "ProductItem", "handicraft", "Sản phẩm được làm thủ công, thường phản ánh kỹ thuật, vật liệu và văn hóa của địa phương.", aliases=[("Hàng thủ công", "vi"), ("Handicraft", "en")], product_category="handicraft"),
    item("product_item_local_specialty", "Đặc sản địa phương", "ProductItem", "local_specialty", "Sản phẩm đặc trưng của địa phương có thể mua mang về làm quà hoặc sử dụng sau chuyến đi.", aliases=[("Đặc sản làm quà", "vi")], product_category="local_specialty"),
    item("product_item_postcard", "Bưu thiếp", "ProductItem", "postcard", "Ấn phẩm nhỏ có hình ảnh điểm đến, thường dùng làm kỷ niệm hoặc gửi tặng.", aliases=[("Postcard", "en")], product_category="souvenir"),
    item("product_item_traditional_clothing", "Trang phục truyền thống", "ProductItem", "traditional_clothing", "Trang phục hoặc phụ kiện mang đặc trưng văn hóa truyền thống của địa phương hay cộng đồng.", aliases=[("Traditional clothing", "en")], product_category="clothing"),
]


# Keep this batch strictly scoped to the entries in more-node.yaml. The longer
# expansion lists above are deliberately excluded after the user narrowed the
# requested scope.
CANDIDATES = [
    *ACTIVITIES[:13],
    *DRINK_ITEMS[:5],
    *FOOD_ITEMS[:35],
    *PRODUCT_ITEMS[:1],
]
REUSED = {
    "Activity": ["Đi dạo ngoài trời", "Hát karaoke", "Thư giãn và chăm sóc sức khỏe"],
    "DrinkItem": ["Cà phê", "Trà"],
    "FoodItem": ["Phở"],
}


def _property_value(value: object) -> str:
    if isinstance(value, (dict, list)):
        return _json(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    ids = [str(candidate["id"]) for candidate in CANDIDATES]
    normalized_pairs = [
        (str(candidate["type"]), normalize_knowledge_text(str(candidate["name"])))
        for candidate in CANDIDATES
    ]
    if len(ids) != len(set(ids)) or len(normalized_pairs) != len(set(normalized_pairs)):
        raise RuntimeError("Duplicate ID or normalized type/name inside curated candidates")

    with SessionLocal() as db:
        edges_before = db.scalar(select(func.count()).select_from(KnowledgeRelationship)) or 0
        existing_ids = set(db.scalars(select(KnowledgeEntity.id).where(KnowledgeEntity.id.in_(ids))))
        existing_name_rows = db.execute(
            select(KnowledgeEntity.id, KnowledgeEntity.entity_type, KnowledgeEntity.normalized_name).where(
                KnowledgeEntity.entity_type.in_({str(candidate["type"]) for candidate in CANDIDATES}),
                KnowledgeEntity.normalized_name.in_({pair[1] for pair in normalized_pairs}),
            )
        ).all()
        existing_by_pair = {(row.entity_type, row.normalized_name): row.id for row in existing_name_rows}
        conflicts = []
        for candidate in CANDIDATES:
            pair = (str(candidate["type"]), normalize_knowledge_text(str(candidate["name"])))
            matched_id = existing_by_pair.get(pair)
            if str(candidate["id"]) in existing_ids or matched_id:
                conflicts.append(
                    {
                        "candidateId": candidate["id"],
                        "name": candidate["name"],
                        "matchedId": matched_id,
                    }
                )

        reused_results: dict[str, dict[str, str | None]] = {}
        for entity_type, names in REUSED.items():
            reused_results[entity_type] = {}
            for name in names:
                reused_results[entity_type][name] = db.scalar(
                    select(KnowledgeEntity.id).where(
                        KnowledgeEntity.entity_type == entity_type,
                        KnowledgeEntity.normalized_name == normalize_knowledge_text(name),
                    )
                )

        missing_reused = {
            entity_type: [name for name, entity_id in names.items() if entity_id is None]
            for entity_type, names in reused_results.items()
            if any(entity_id is None for entity_id in names.values())
        }
        by_type: dict[str, int] = {}
        for candidate in CANDIDATES:
            entity_type = str(candidate["type"])
            by_type[entity_type] = by_type.get(entity_type, 0) + 1

        report: dict[str, object] = {
            "mode": "apply" if args.apply else "dry-run",
            "source": SOURCE,
            "candidateNodes": len(CANDIDATES),
            "byType": by_type,
            "conflicts": conflicts,
            "reused": reused_results,
            "missingReused": missing_reused,
            "edgesBefore": edges_before,
        }
        if conflicts or missing_reused:
            report["applied"] = False
            print(json.dumps(report, ensure_ascii=False, indent=2))
            raise SystemExit(2)

        if args.apply:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for candidate in CANDIDATES:
                entity = KnowledgeEntity(
                    id=str(candidate["id"]),
                    canonical_name=str(candidate["name"]),
                    normalized_name=normalize_knowledge_text(str(candidate["name"])),
                    entity_type=str(candidate["type"]),
                    status="draft",
                    created_at=now,
                    updated_at=now,
                )
                db.add(entity)
                for key, value in dict(candidate["properties"]).items():
                    db.add(
                        KnowledgeProperty(
                            entity_id=entity.id,
                            key=key,
                            value=_property_value(value),
                            source=SOURCE,
                            note=NOTE,
                            updated_at=now,
                        )
                    )
                for alias, language in list(candidate["aliases"]):
                    db.add(
                        KnowledgeAlias(
                            entity_id=entity.id,
                            alias=alias,
                            normalized_alias=normalize_knowledge_text(alias),
                            language=language,
                            alias_type="alternate_name",
                            source=SOURCE,
                            provider="manual_curation",
                            status="imported",
                            confidence=1.0,
                            created_at=now,
                        )
                    )
            db.commit()

        edges_after = db.scalar(select(func.count()).select_from(KnowledgeRelationship)) or 0
        report["edgesAfter"] = edges_after
        report["edgesCreated"] = edges_after - edges_before
        report["applied"] = bool(args.apply)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
