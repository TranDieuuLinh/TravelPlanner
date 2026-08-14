# Phase 06 — Integration tests, observability và rollout

Cập nhật lần cuối: 2026-08-14

## Test matrix

- Unit: normalization, confidence, conflict merge, stale/expiry.
- Contract: camelCase/snake_case, unknown fact type, max sizes.
- Repository: transaction, version conflict, restart persistence, concurrent writes.
- Graph: same-thread follow-up, new-thread isolation, missing-memory fallback.
- Agent integration: Explorer/Place Checker/Planner dùng đúng projection.
- Regression: URL places không bị thay bởi system suggestions.
- Security: prompt injection trong transcript không đổi memory policy.

## Observability

Ghi metadata không nhạy cảm: `chat_id`, memory version trước/sau, facts added/updated/stale, reference count, route, source count, duration và fallback code. Không log raw prompt, third-party payload hoặc secret.

TripChat đã ghi structured log `trip_chat_memory_metrics` với các trường trên.
Prompt-injection-like transcript được chặn ở extractor trước khi tạo fact.

## Rollout

1. Feature flag `conversation_memory_enabled=false` để rollback về transcript-only.
2. Shadow extraction: tạo facts nhưng chưa route theo facts.
3. So sánh route/clarification với baseline.
4. Bật read-only memory cho internal test.
5. Bật write + resolve theo nhóm request.
6. Có rollback về transcript-only fallback.

## Definition of Done

- Test phase pass.
- `python -m compileall src` pass.
- Frontend/backend integration pass.
- `docs/schema.md`, `docs/database-schema.md` và migration docs được cập nhật.
- Backend file không vượt 400 dòng nếu có thể tách.
- Có báo cáo latency/token trước và sau memory.

## Trạng thái triển khai

- Unit, contract, repository, root graph, agent integration và security tests đã
  được bổ sung/chạy trong backend.
- Latency/token production chưa được đánh giá trên traffic thật; chỉ có số liệu
  test cục bộ. Không coi kết quả hiện tại là SLO production.
