# Frontend feature boundaries

Mỗi thư mục con sở hữu code của một domain UI. Route trong `src/app` chỉ ghép
page; API client, type, component, hook và utility nghiệp vụ nằm cạnh feature
đã sở hữu chúng.

```text
features/<feature>/
├── api.ts hoặc api/       # gọi backend của feature
├── components/            # UI chỉ dùng cho feature
├── hooks/                 # lifecycle/state orchestration
├── lib/                   # pure helper và unit test colocated
└── types.ts               # contract TypeScript của feature
```

Code không thuộc riêng domain nào đi vào `src/shared`. `src/components` chỉ giữ
app shell hoặc visual primitive dùng xuyên feature. Không import ngược từ
`shared` vào `features`.
