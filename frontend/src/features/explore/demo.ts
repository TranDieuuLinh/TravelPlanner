// Lightweight discovery fixtures keep the mixed-media feed useful while the
// community API is empty. They are intentionally presentation-only mock data.
export const mockExplorePosts = [
  {
    id: "mock-hoi-an-reel",
    contentType: "reel" as const,
    caption: "Một sáng thật chậm giữa những mái ngói vàng của Hội An.",
    mediaUrl: "https://videos.pexels.com/video-files/3015510/3015510-hd_1920_1080_24fps.mp4",
    locationName: "Hội An · Quảng Nam",
    createdAt: "2026-08-02T08:00:00.000Z",
    authorName: "Linh đi đâu",
    authorAvatarUrl: null,
  },
  {
    id: "mock-ha-noi-photo",
    contentType: "post" as const,
    caption: "Những góc phố Hà Nội đẹp nhất lúc thành phố vừa lên đèn.",
    mediaUrl: "https://images.unsplash.com/photo-1555921015-5532091f6026?auto=format&fit=crop&w=1200&q=85",
    locationName: "Phố cổ · Hà Nội",
    createdAt: "2026-08-01T18:30:00.000Z",
    authorName: "An Eats",
    authorAvatarUrl: null,
  },
  {
    id: "mock-ha-giang-reel",
    contentType: "reel" as const,
    caption: "Săn mây trên cung đường Hà Giang, mỗi khúc cua là một khung hình mới.",
    mediaUrl: "https://videos.pexels.com/video-files/2169880/2169880-hd_1920_1080_30fps.mp4",
    locationName: "Mèo Vạc · Hà Giang",
    createdAt: "2026-07-30T06:15:00.000Z",
    authorName: "Việt Trip",
    authorAvatarUrl: null,
  },
  {
    id: "mock-da-nang-photo",
    contentType: "post" as const,
    caption: "Một buổi chiều xanh trong bên bờ biển Đà Nẵng.",
    mediaUrl: "https://images.unsplash.com/photo-1537996194471-e657df975ab4?auto=format&fit=crop&w=1200&q=85",
    locationName: "Sơn Trà · Đà Nẵng",
    createdAt: "2026-07-29T15:45:00.000Z",
    authorName: "Mai Hương",
    authorAvatarUrl: null,
  },
];
