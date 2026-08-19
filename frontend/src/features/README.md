# Frontend feature boundaries

Cập nhật lần cuối: 2026-08-15.

Mỗi thư mục con sở hữu code của một domain UI. Route trong `src/app` chỉ ghép
page; API client, type, component, hook và utility nghiệp vụ nằm cạnh feature
đã sở hữu chúng.

```text
features/<feature>/
├── api.ts hoặc api/       # gọi backend của feature
├── contracts/             # contract domain dùng chung giữa API, model và UI
├── components/            # UI chỉ dùng cho feature
├── hooks/                 # lifecycle/state orchestration
├── lib/                   # pure helper và unit test colocated
├── model/                 # state transition, policy và formatter thuần của feature
└── types.ts               # contract TypeScript của feature
```

Feature lớn có thể giữ một facade API tương thích để re-export contract và
operation trong lúc tách dần theo capability. Code mới phải import từ
`contracts/` hoặc API capability trực tiếp khi không cần facade.

Code không thuộc riêng domain nào đi vào `src/shared`. `src/components` chỉ giữ
app shell hoặc visual primitive dùng xuyên feature. Không import ngược từ
`shared` vào `features`.
