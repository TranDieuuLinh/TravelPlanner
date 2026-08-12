# Task 01: Contract và validation

## Mục tiêu

Định nghĩa Pydantic contract nhận đúng output camelCase của Explorer và từ chối
request-level data sai trước
khi gọi KG, database, LLM hoặc external tool.

## Phụ thuộc

Không có. Đây là task triển khai đầu tiên.

## Các model

Tối thiểu cần định nghĩa:

- `PlaceCheckerInput`;
- `SourcePlaceEvidence`;
- `PlaceCandidateInput`;
- `InputItem` và `UrlNote`;
- `BudgetInput` và `PeopleInput`;
- enum cho lifecycle, verification, source tier, severity và output status.

JSON từ Explorer dùng camelCase: `inputADM`, `addressHint`, `sourcePlaces`,
`evidenceType`, `observedAt`, `inputItems`, `relatedPlaceName`, `urlNotes`,
`targetAmount`, `shortPreferences` và `shortAvoids`. Field Python giữ
snake_case. Contract vẫn nhận snake_case để các service nội bộ và dữ liệu cũ
không bị hỏng.

## Quy tắc kiểm tra dữ liệu

- Trim `inputADM` và bắt buộc non-empty.
- `days` nằm trong 1-30.
- Confidence nằm trong 0-1.
- Latitude và longitude nếu có phải xuất hiện cùng nhau và nằm trong range hợp lệ.
- Explorer candidate phải có ít nhất một record trong `sourcePlaces`.
- Evidence origin phải là `input`, `url` hoặc source đã đăng ký rõ ràng.
- `urlNotes=null` được chuẩn hóa thành `[]`.
- `observedAt` nếu có phải parse được thành datetime hợp lệ.
- `relatedPlaceName` là liên kết mềm từ item tới place đã được Explorer nhận diện.
- Số people không âm và tổng people phải lớn hơn 0.
- `target_amount` nếu có phải không âm và phải có currency; `basis` nhận
  `per_person` hoặc `group_total`. Explorer chuyển group total về per-person
  trước handoff, còn default `per_person` giữ tương thích input cũ.
- Preference và avoid array rỗng là hợp lệ.

Candidate malformed nên trở thành candidate-level validation issue nếu có thể
khôi phục an toàn. Destination, duration, people hoặc budget structure sai là
request-level failure.

## Các bước triển khai

1. Thêm contract model và enum.
2. Thêm field/model validator và normalize nullable note.
3. Thêm structured candidate validation issue model.
4. Thêm serialization test để ngăn day/route field lọt vào contract.

## Test

- Parse nguyên payload camelCase Hanoi của Explorer và serialize alias ngược lại.
- Normalize null note.
- Reject ADM rỗng, day 0/day 31, confidence sai, people âm, total people bằng 0
  và budget malformed.
- Reject tọa độ thiếu một vế hoặc ngoài range.
- Bảo toàn raw evidence, address hint và source time hint.
- Xác nhận không provider nào được gọi.

## Điều kiện hoàn thành

Input mẫu validate thành công, request-level field sai fail có dự đoán,
candidate issue có thể khôi phục được giữ lại và focused contract test pass.
