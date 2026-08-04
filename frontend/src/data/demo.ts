export type MarketPlan = {
  id: number;
  title: string;
  place: string;
  creator: string;
  days: number;
  price: string;
  rating: string;
  saves: string;
  tag: string;
  tone: string;
  summary: string;
};

export const marketPlans: MarketPlan[] = [
  { id: 1, title: "Đà Nẵng & Hội An cho hội mê ăn", place: "Đà Nẵng", creator: "Linh đi đâu", days: 4, price: "149.000đ", rating: "4,9", saves: "1,2k", tag: "Ẩm thực", tone: "sunset", summary: "Biển, phố cổ và các quán địa phương đã được chọn lọc." },
  { id: 2, title: "Hà Giang: cung đường đầu tiên", place: "Hà Giang", creator: "Việt Trip", days: 4, price: "189.000đ", rating: "4,8", saves: "980", tag: "Road trip", tone: "forest", summary: "Lộ trình vừa sức, điểm nghỉ và lưu ý cho người đi lần đầu." },
  { id: 3, title: "48 giờ ăn hết Hải Phòng", place: "Hải Phòng", creator: "An Eats", days: 2, price: "79.000đ", rating: "4,9", saves: "2,1k", tag: "Tiết kiệm", tone: "berry", summary: "Food tour ngắn ngày với ngân sách phù hợp sinh viên." },
  { id: 4, title: "Đà Lạt sống chậm", place: "Đà Lạt", creator: "Mai Hương", days: 3, price: "129.000đ", rating: "4,7", saves: "1,7k", tag: "Thư giãn", tone: "mist", summary: "Rừng thông, cà phê và những buổi sáng không vội." },
  { id: 5, title: "Ninh Bình cuối tuần", place: "Ninh Bình", creator: "Minh Go", days: 2, price: "99.000đ", rating: "4,8", saves: "1,4k", tag: "Thiên nhiên", tone: "lime", summary: "Ít di chuyển nhưng vẫn đủ những trải nghiệm đáng nhớ." },
  { id: 6, title: "Phú Yên: biển vắng và làng chài", place: "Phú Yên", creator: "Trang Local", days: 3, price: "139.000đ", rating: "4,8", saves: "1,4k", tag: "Biển", tone: "ocean", summary: "Các bãi biển ít người biết cùng trải nghiệm địa phương." }
];
