# Dữ liệu routing cục bộ

Valhalla và OpenTripPlanner tự host không cần API key. Chúng vẫn cần dữ liệu
đầu vào:

- Valhalla: file OpenStreetMap PBF. Compose tải dữ liệu Việt Nam từ Geofabrik ở
  lần build tile đầu tiên.
- OpenTripPlanner: một file OSM PBF và ít nhất một feed GTFS Schedule có
  `gtfs` trong tên file. GTFS-RT là tùy chọn cho thông tin realtime.

## Chuẩn bị OpenTripPlanner

Giữ file nguồn Việt Nam ngoài thư mục OTP và cắt một extract đủ nhỏ cho vùng
đang phục vụ. Ví dụ bbox Hà Nội mở rộng:

```bash
docker run --rm \
  -v "$PWD/routing-data:/data" \
  debian:trixie-slim sh -lc \
  'apt-get update &&
   apt-get install -y --no-install-recommends osmium-tool &&
   osmium extract --bbox 105.2,20.4,106.3,21.7 --set-bounds \
     /data/osm-source/vietnam-latest.osm.pbf \
     -o /data/opentripplanner/hanoi-region.osm.pbf'
```

Đặt feed `<khu-vuc>-gtfs.zip` cạnh extract trong
`routing-data/opentripplanner/`. Chỉ để một file OSM PBF trong thư mục này.
Feed GTFS phải đến từ cơ quan vận tải hoặc nguồn có quyền sử dụng rõ ràng và còn
mới. Không commit các file dữ liệu lớn vào repository.

Compose tự chạy `--build --save` khi thiếu `graph.obj`, sau đó chuyển sang
`--load --serve`. Heap mặc định 2500 MB để nằm trong giới hạn RAM khoảng 4 GB
của Docker Desktop. Chạy stack:

```bash
docker compose --profile routing up --build
```

Endpoint mặc định:

- Valhalla: `http://localhost:8002`
- OpenTripPlanner GraphQL: `http://localhost:8080/otp/gtfs/v1`

Nếu chưa chạy hai dịch vụ, backend vẫn hoạt động nhưng route đường bộ sẽ mang
nhãn `geodesic_estimate`; lựa chọn bus sẽ không xuất hiện.

Feed nguồn `gtfs-source/hanoi-gtfs-am-2018.zip` là dữ liệu cũ. Để UI
development có thể kiểm tra luồng bus, tạo bản sao dịch ngày (không phải lịch
hiện hành):

```bash
python3 routing-data/prepare_dev_gtfs.py \
  routing-data/gtfs-source/hanoi-gtfs-am-2018.zip \
  routing-data/opentripplanner/hanoi-gtfs-dev-shifted.zip
```

Backend gắn `scheduleStatus=development_shifted_2018`, đặt `verified=false` và
UI hiển thị cảnh báo cho mọi route từ fixture này. Khi có feed chính thức/có
license rõ và còn hiệu lực, thay file dev, đặt
`OPENTRIPPLANNER_SCHEDULE_STATUS=current`, xóa `graph.obj`, rồi khởi động lại
profile routing để rebuild.
