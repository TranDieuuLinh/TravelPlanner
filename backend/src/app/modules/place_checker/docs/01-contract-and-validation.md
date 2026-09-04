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

JSON từ Explorer dùng camelCase: `inputADM`, `sourcePlaces`, `evidenceType`,
`sourceUrl`, `sourceTimeHint`, `addressHint`, nested `urlNotes`, `inputItems`,
`relatedPlaceName`, `amountPerPerson`, `shortPreferences`, `shortAvoids` và
`specialNotes`. Field Python giữ snake_case.

Runtime metadata `platform`, `extractorVersion`, `modelVersion` và `cacheStatus`
không thuộc handoff contract. Explorer có thể giữ chúng trong telemetry nội bộ,
nhưng PlaceChecker chỉ nhận evidence cần cho resolution và planning.

## Quy tắc kiểm tra dữ liệu

- Trim `inputADM` và bắt buộc non-empty.
- `days` nằm trong 1-30.
- Latitude và longitude nếu có phải xuất hiện cùng nhau và nằm trong range hợp lệ.
- Explorer candidate phải có ít nhất một record trong `sourcePlaces`.
- `evidenceType` chỉ là `raw_prompt` hoặc `url`; URL type bắt buộc có
  `sourceUrl`, còn raw prompt bắt buộc không có URL.
- `sourcePlaces[].urlNotes` mặc định là `[]` và mỗi note chỉ có `summary`.
- `relatedPlaceName` là liên kết mềm từ item tới place đã được Explorer nhận diện.
- Số people không âm và tổng people phải lớn hơn 0.
- `amountPerPerson` nếu có phải không âm; currency là mã ba chữ cái. Explorer
  chuyển group total về per-person trước handoff.
- Preference và avoid array rỗng là hợp lệ.

Candidate malformed nên trở thành candidate-level validation issue nếu có thể
khôi phục an toàn. Destination, duration, people hoặc budget structure sai là
request-level failure.

## Các bước triển khai

1. Thêm contract model và enum.
2. Thêm field/model validator cho evidence type, URL và nested note.
3. Thêm structured candidate validation issue model.
4. Thêm serialization test để ngăn day/route field lọt vào contract.

## Test

- Parse nguyên payload camelCase Hanoi của Explorer và serialize alias ngược lại.
- Normalize nested note rỗng.
- Reject ADM rỗng, day 0/day 31, people âm, total people bằng 0
  và budget malformed.
- Reject tọa độ thiếu một vế hoặc ngoài range.
- Bảo toàn address hint, source URL, source time hint và note summary.
- Xác nhận serialized payload không có tags/confidence/provenance nội bộ.
- Xác nhận không provider nào được gọi.

## Điều kiện hoàn thành

Input mẫu validate thành công, request-level field sai fail có dự đoán,
candidate issue có thể khôi phục được giữ lại và focused contract test pass.
