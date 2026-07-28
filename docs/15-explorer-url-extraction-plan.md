# Explorer URL extraction plan

This plan covers the testing-only flow for Explorer. The goal is to accept a raw
user request, a destination, and optional video/reel URLs; extract useful travel
signals; normalize them through Explorer; and return JSON to the frontend.

This version does not persist to DB yet.

## Target flow

```text
rawRequest + destination + optional urls
  -> URL loader
  -> video/audio extractor
  -> speech-to-text
  -> OCR/frame text extraction
  -> place/context extraction
  -> Explorer
  -> return JSON
```

## API

Use the normal Explorer endpoint, even while this is testing-only:

```text
POST /api/trips/explore
```

Request:

```json
{
  "rawRequest": "Tạo lịch trình Đà Nẵng 3 ngày từ vài reels đồ ăn",
  "destination": "Da Nang",
  "urls": [],
  "placeCandidates": [],
  "userState": {},
  "tripSpec": {
    "days": null,
    "partySize": null,
    "startDate": null,
    "endDate": null,
    "accommodation": {},
    "transport": {},
    "budget": {}
  }
}
```

Only `rawRequest` and `destination` are required. The frontend may send empty
arrays/objects for the rest.

Response:

```json
{
  "intent": {
    "destination": "Da Nang",
    "budgetLevel": "balanced",
    "travelStyle": "local",
    "pace": "balanced",
    "interests": ["food", "coffee"],
    "mustVisitPlaces": [],
    "avoidPlaces": [],
    "constraints": [],
    "clarifyingQuestions": []
  },
  "tripSpec": {
    "days": 3,
    "partySize": 2,
    "startDate": null,
    "endDate": null,
    "accommodation": {
      "required": true,
      "hotelArea": null,
      "checkInDate": null,
      "checkOutDate": null,
      "roomCount": 1,
      "guestCount": 2,
      "preferences": []
    },
    "transport": {
      "required": true,
      "preferredModes": ["mixed"],
      "avoidModes": [],
      "includeBetweenPlaces": true,
      "includeArrivalDeparture": true
    },
    "budget": {
      "totalBudget": null,
      "perPersonBudget": null,
      "includeFood": true,
      "includeTransport": true,
      "includeHotel": true,
      "includeTickets": true
    }
  },
  "placeCandidates": [
    {
      "name": "Quan mi quang A",
      "placeId": null,
      "address": "12 Nguyen Hue, Da Nang",
      "source": "url_reel",
      "sourceUrl": "https://www.instagram.com/reel/...",
      "confidence": 0.82,
      "priority": 1,
      "notes": "Extracted from transcript and metadata text"
    }
  ],
  "urlReelSignals": [
    {
      "url": "https://www.instagram.com/reel/...",
      "platform": "instagram",
      "extractedPlaces": ["Quan mi quang A"],
      "extractedPlaceDetails": [
        {
          "name": "Quan mi quang A",
          "placeId": null,
          "address": "12 Nguyen Hue, Da Nang",
          "source": "url_reel",
          "sourceUrl": "https://www.instagram.com/reel/...",
          "confidence": 0.82,
          "priority": 1,
          "notes": "Transcript mentioned this address"
        }
      ],
      "interests": ["food"],
      "constraints": [],
      "confidence": 0.82,
      "notes": ["extracted from transcript and metadata"]
    }
  ],
  "assumptions": [],
  "missingInfoQuestions": [],
  "debug": {
    "transcript": "...",
    "rawExtractedText": "..."
  }
}
```

`debug` is useful during testing but should not be part of the production
response.

## Module layout

Add the URL extraction tool under Explorer:

```text
backend/app/modules/plans/explorer/tools/url_reels/
  schema.py
  loader.py
  media.py
  speech_to_text.py
  ocr.py
  extractor.py
  service.py
```

Suggested responsibility:

```text
schema.py
  Pydantic models for URL extraction input/output.

loader.py
  Detect platform, fetch URL metadata, and decide whether media can be loaded.

media.py
  Extract downloadable video/audio references when possible.

speech_to_text.py
  Convert audio to transcript through a provider interface.

ocr.py
  Sample frames and extract visible text through a provider interface.

extractor.py
  Convert rawRequest/transcript/OCR text into place candidates, interests, and constraints.

service.py
  Orchestrate loader -> media -> STT -> OCR -> extractor for one or more URLs.
```

## Contracts

### Explore request

```json
{
  "rawRequest": "Tạo lịch trình Đà Nẵng 3 ngày từ vài reels đồ ăn",
  "destination": "Da Nang",
  "urls": [],
  "placeCandidates": [],
  "userState": {},
  "tripSpec": {}
}
```

Rules:

- `rawRequest` is required.
- `destination` is required.
- `urls` is optional; if empty, Explorer runs from `rawRequest` + `destination`.
- `placeCandidates` is optional; if empty, extraction can still infer candidates from `rawRequest` or URLs.
- `userState` is optional.
- `tripSpec` is optional; if empty, Explorer returns defaults and may ask follow-up questions.
- URL processing failure should not fail the whole request unless all inputs are unusable.

### URL extraction result

```json
{
  "url": "https://www.instagram.com/reel/...",
  "platform": "instagram",
  "status": "extracted",
  "transcript": "...",
  "ocrText": "...",
  "placeCandidates": [],
  "interests": [],
  "constraints": [],
  "warnings": []
}
```

Statuses:

```text
queued
loading
media_extracted
transcribed
ocr_extracted
extracted
failed
```

For testing, these statuses can exist only in memory and appear in debug output.
When DB persistence is added later, they can map to `source_imports.status`.

## Step-by-step implementation

### Step 1: Request schema

Create `ExploreRequest`.

Fields:

```text
destination
rawRequest
urls
placeCandidates
userState
tripSpec
```

Create `ExploreResponse`.

Fields:

```text
intent
tripSpec
placeCandidates
urlReelSignals
assumptions
missingInfoQuestions
debug
```

### Step 2: URL loader

The loader should detect platform from the URL:

```text
instagram
tiktok
youtube
unknown
```

For testing, the first version can return a stub metadata object instead of
downloading real media.

Important: do not let platform-specific payloads leak into Explorer. Normalize
everything into internal schemas.

### Step 3: Media extraction

The media extractor should return:

```text
videoPath or videoUrl
audioPath or audioUrl
thumbnail/frame references
```

For testing, this can be a no-op when direct media download is not available.

Failure behavior:

```text
If media extraction fails:
  continue with URL metadata + rawRequest
  add warning
```

### Step 4: Speech-to-text

Create a provider interface:

```text
SpeechToTextProvider.transcribe(audio) -> transcript
```

Testing providers:

```text
StubSpeechToTextProvider
```

Later providers:

```text
OpenAI transcription
Whisper local
Other STT service
```

The STT output should include:

```text
text
language
confidence if available
segments if available
```

### Step 5: OCR/frame text extraction

Create a provider interface:

```text
OcrProvider.extract_text(frames) -> ocrText
```

Testing providers:

```text
StubOcrProvider
```

Later providers:

```text
Vision model
Tesseract/local OCR
Cloud OCR
```

The OCR output should include:

```text
text
frame timestamps if available
confidence if available
```

### Step 6: Place/context extraction

Input:

```text
rawRequest
transcript
ocrText
destination
```

Output:

```text
placeCandidates
interests
constraints
assumptions
warnings
```

Rules:

- Extracted places become `placeCandidates`.
- `source` should be `raw_request`, `url_reel`, or `user`.
- `sourceUrl` should be filled when candidate came from URL.
- Low-confidence names should stay candidates, not final itinerary items.
- Deduplicate by normalized name.

Example:

```json
{
  "name": "Quan mi quang A",
  "source": "url_reel",
  "sourceUrl": "https://www.instagram.com/reel/...",
  "confidence": 0.82,
  "priority": 1,
  "notes": "Mentioned in transcript"
}
```

### Step 7: Explorer normalization

Explorer receives:

```text
destination
rawRequest
tripSpec
placeCandidates
urlReelSignals
```

Explorer returns:

```text
intent
tripSpec
placeCandidates
assumptions
missingInfoQuestions
trace
```

Explorer should not create final itinerary items. That belongs to Finder later.

### Step 8: Return JSON to frontend

The explore endpoint returns the full Explorer result plus debug extraction
details.

For testing, include:

```text
debug.transcript
debug.ocrText
debug.rawExtractedText
debug.urlStatuses
```

For production, remove or restrict debug fields.

## Error handling

URL extraction can fail independently.

Example partial success response:

```json
{
  "intent": {},
  "placeCandidates": [],
  "urlReelSignals": [],
  "warnings": [
    "Could not extract media from https://www.instagram.com/reel/..."
  ],
  "debug": {
    "urlStatuses": [
      {
        "url": "https://www.instagram.com/reel/...",
        "status": "failed",
        "reason": "media unavailable"
      }
    ]
  }
}
```

Only return a hard error when:

- `rawRequest` is missing.
- `destination` is missing.

## Testing plan

### Raw request only

Input:

```json
{
  "rawRequest": "Tạo lịch trình Đà Nẵng 3 ngày ăn uống và cà phê",
  "destination": "Da Nang",
  "urls": [],
  "placeCandidates": [],
  "userState": {},
  "tripSpec": {}
}
```

Expected:

```text
intent.destination = Da Nang
intent.interests includes food/coffee
placeCandidates may be empty
missingInfoQuestions may ask days, budget, or party size if absent
```

### Raw request + URL

Input:

```json
{
  "rawRequest": "Tạo lịch trình từ reel này",
  "destination": "Da Nang",
  "urls": ["https://www.instagram.com/reel/..."],
  "placeCandidates": [],
  "userState": {},
  "tripSpec": {}
}
```

Expected:

```text
urlReelSignals has one item
placeCandidates includes extracted places if STT/OCR has enough signal
```

### Full optional request

Input:

```json
{
  "rawRequest": "Tạo lịch trình Đà Nẵng 3 ngày, đồ ăn và cà phê, đi 2 người",
  "destination": "Da Nang",
  "urls": ["https://www.instagram.com/reel/..."],
  "placeCandidates": [
    {
      "name": "Son Tra",
      "placeId": null,
      "source": "user",
      "sourceUrl": null,
      "confidence": 1,
      "priority": 1,
      "notes": "User mentioned this place"
    }
  ],
  "userState": {
    "userId": "user_123",
    "locale": "vi-VN",
    "timezone": "Asia/Ho_Chi_Minh",
    "travelPreferences": ["food", "coffee"]
  },
  "tripSpec": {
    "days": 3,
    "partySize": 2,
    "startDate": null,
    "endDate": null,
    "accommodation": {
      "required": true,
      "hotelArea": null,
      "checkInDate": null,
      "checkOutDate": null,
      "roomCount": 1,
      "guestCount": 2,
      "preferences": []
    },
    "transport": {
      "required": true,
      "preferredModes": ["mixed"],
      "avoidModes": [],
      "includeBetweenPlaces": true,
      "includeArrivalDeparture": true
    },
    "budget": {
      "totalBudget": null,
      "perPersonBudget": null,
      "includeFood": true,
      "includeTransport": true,
      "includeHotel": true,
      "includeTickets": true
    }
  }
}
```

Expected:

```text
intent combines rawRequest and URL interests
placeCandidates deduplicates rawRequest and URL places
debug includes transcript/OCR if available
```

## Later DB version

When moving beyond testing, persist these tables:

```text
trips
source_imports
place_candidates
trip_explorations
```

Later production flow:

```text
User rawRequest + destination + optional urls
  -> Explorer extraction
  -> Save DB
  -> Planner reads DB
  -> Finder reads DB/planner output
```

For now, stop at:

```text
Explorer -> return JSON
```
