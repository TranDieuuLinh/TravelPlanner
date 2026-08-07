# Bản đồ module codebase

Tài liệu này mô tả code đang tồn tại, không phải toàn bộ tầm nhìn sản phẩm.

## Ứng dụng người dùng (`frontend/`)

- `src/app`: route Next.js App Router. Route Planner chỉ chuyển quyền render
  sang feature, tránh đặt implementation lớn ngay trong routing tree.
- `src/features/auth`: session cookie, refresh và auth context.
- `src/features/planner`: API/schema plan và trip chat; URL job cho guest; chat,
  discovery, map, itinerary; hook conversation turn; helper route, note, source,
  transport và thứ tự lịch trình. Pure helper đặt test cạnh file.
- `src/features/marketplace`: listing, favorite, review, report và moderation
  client contract.
- `src/features/orders`: checkout, order detail và copy plan cho buyer.
- `src/features/profile`: hồ sơ, bài public, traveler preference và visited map.
- `src/features/travel-groups`: tìm/join group và đăng bài trong group.
- `src/features/places`: API admin review place trùng.
- `src/features/explore`: dữ liệu demo còn dùng bởi feed hiện tại.
- `src/shared/api`: HTTP transport, CSRF và single-flight session refresh.
- `src/components`: app shell và Penguin visual dùng xuyên feature.

## Planning Control (`admin-frontend/`)

- `app/(dashboard)/runs`: danh sách và chi tiết planning run.
- `app/(dashboard)/golden`: chạy golden case qua runtime thật.
- `app/(dashboard)/knowledge-graph`: duyệt entity, import AI và quan hệ graph.
- `app/(dashboard)/tools`: công cụ thử research theo vùng/constraint/festival.
- `lib/api.ts`: client cho planning runs, golden dataset và tool endpoints.
- `lib/knowledge-graph.ts`: contract/client Knowledge Graph admin.

Đây là ứng dụng nội bộ riêng, không phải route admin của frontend người dùng.

## Backend modular monolith (`backend/app/`)

- `auth`: đăng ký/đăng nhập, JWT cookie, refresh session và CSRF.
- `users`: account, role/status và creator application data.
- `profiles`: showcase, visited place, post media và hồ sơ người dùng.
- `preferences`: traveler profile dài hạn và preference signal.
- `travel_groups`: group, membership và post.
- `plans`: domain plan, Explorer/import URL, conversation supervisor, trip chat,
  theme planning, place selection, route, check, mutation, Main/Backup workflow
  và background URL job. Đây là module lớn nhất và là hotspot chính.
- `places`: catalog place, alias, eligibility, resolution và region statistics.
- `knowledge_graph`: ontology, import review, PostgreSQL repository, search và
  graph-backed research.
- `planning_runs`: snapshot đã redaction, golden dataset/runner và API quan sát.
- `marketplace`: listing/version, favorite, review, report, moderation và audit.
- `orders`: checkout, webhook payment, entitlement và buyer plan copy.
- `payments`: adapter MoMo.
- `integrations`: adapter LLM, media storage, routing và web search sau interface.
- `shared/contracts`: contract liên module, nổi bật là Planner–Marketplace.

Router chỉ xử lý HTTP; nghiệp vụ đi qua service/workflow/domain; persistence đi
qua repository. `app/api_router.py` là composition root của API.

## Dữ liệu và công cụ hỗ trợ

- `crawl_knowledge_travel`: package crawler có collector, HTTP policy, normalize,
  storage và pipeline dựng graph; không chạy trong request backend.
- `database`: golden dataset, relational export và script import festival.
- `tool-crawl/crawl-price`: job nghiên cứu giá có nguồn cho TravelPlace.
- `routing-data`: input và volume cho Valhalla/OpenTripPlanner.
- `read_data_parquet`: utility đọc Parquet và xuất thẳng relational CSV.
- `scripts` và `backend/scripts`: migration/evaluation/maintenance one-off.

## Hotspot còn lại

- `features/planner/components/PlannerPage.tsx` và `PlannerMap.tsx` vẫn rất lớn;
  nên tách tiếp theo state machine/intake, itinerary editor và directions panel
  bằng component/hook có test trước khi thay đổi hành vi.
- Backend `plans`, `places/resolver.py` và `place_selector/service.py` có độ phức
  tạp cao. Chỉ tách khi đã khóa contract bằng test, tránh di chuyển đồng thời với
  thay đổi thuật toán Planner.
- Planning Control Knowledge Graph page còn gộp nhiều panel trong một file; có
  thể chia component theo entity/import/relationship khi UI tiếp tục mở rộng.
