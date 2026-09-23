# Flight Transport Service ✈️

Production-ready FastAPI microservice for searching flights using **SerpApi Google Flights API** (`engine=google_flights`).

---

## 📌 Features

- **Google Flights Integration**: Fetches live flights through SerpApi.
- **Combined Flight Results**: Combines `best_flights` and `other_flights` into a single normalized response while maintaining ranking tags (`is_best_flight`).
- **City & Airport Resolution**: Automatically resolves city names (e.g. `Chennai`, `Delhi`, `Coimbatore`) to 3-letter uppercase IATA codes (`MAA`, `DEL`, `CJB`) with support for direct IATA code passthrough.
- **Loosely Coupled Architecture**: Abstract `FlightProvider` protocol allows swapping SerpApi with Amadeus, Skyscanner, or Duffel in the future.
- **Strict Data Integrity**: Missing values are cleanly mapped to `null`; never invents fake data.
- **Robust Error Handling**: Structured JSON error envelopes with error codes for 400, 404, 500, 502, and 504.

---

## 🚀 API Endpoints

### 1. Health Check
```http
GET /health
```
**Response:**
```json
{
  "status": "healthy",
  "service": "flight-service",
  "version": "1.0.0"
}
```

### 2. Search Flights
```http
POST /flights/search
```

#### Request Body
```json
{
  "origin": "Chennai",
  "destination": "Coimbatore",
  "outbound_date": "2026-10-15",
  "return_date": null,
  "travelers": 2,
  "travel_class": "economy",
  "stops": null,
  "currency": "INR",
  "sort_by": "price"
}
```

#### Response Body
```json
{
  "success": true,
  "message": "Found 7 flight options",
  "data": {
    "origin": "MAA",
    "origin_name": "Chennai International Airport",
    "destination": "CJB",
    "destination_name": "Coimbatore International Airport",
    "outbound_date": "2026-10-15",
    "return_date": null,
    "trip_type": "one_way",
    "total_flights": 7,
    "best_flights_count": 1,
    "other_flights_count": 6,
    "flights": [
      {
        "flight_id": "fl_a1b2c3d4e5f67890",
        "airline": "IndiGo",
        "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/6E.png",
        "flight_number": "6E 479",
        "departure_airport": {
          "id": "MAA",
          "name": "Chennai International Airport",
          "time": "2026-10-15 09:55"
        },
        "arrival_airport": {
          "id": "CJB",
          "name": "Coimbatore International Airport",
          "time": "2026-10-15 11:00"
        },
        "departure_time": "2026-10-15 09:55",
        "arrival_time": "2026-10-15 11:00",
        "duration_minutes": 65,
        "duration": "1h 5m",
        "stops": 0,
        "price": 5112.0,
        "currency": "INR",
        "travel_class": "Economy",
        "booking_token": "...",
        "departure_token": null,
        "is_best_flight": true,
        "segments": [
          {
            "airline": "IndiGo",
            "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/6E.png",
            "flight_number": "6E 479",
            "airplane": "Airbus A321neo",
            "travel_class": "Economy",
            "legroom": "28 in",
            "departure_airport": {
              "id": "MAA",
              "name": "Chennai International Airport",
              "time": "2026-10-15 09:55"
            },
            "arrival_airport": {
              "id": "CJB",
              "name": "Coimbatore International Airport",
              "time": "2026-10-15 11:00"
            },
            "duration_minutes": 65,
            "extensions": [
              "Below average legroom (28 in)",
              "Carbon emissions estimate: 43 kg"
            ]
          }
        ],
        "layovers": [],
        "carbon_emissions": {
          "this_flight_grams": 43000,
          "typical_for_route_grams": 44000,
          "difference_percent": -2
        }
      }
    ]
  }
}
```

---

## 🛠️ Environment Variables

Create `.env` inside `transport-service/flight/` or rely on the root `.env`:

| Variable | Description | Default |
|---|---|---|
| `SERPAPI_API_KEY` | SerpApi API key for Google Flights | *(Required)* |
| `FLIGHT_SERVICE_PORT` | Port for the service | `8006` |
| `HTTP_TIMEOUT` | Upstream SerpApi timeout in seconds | `30.0` |
| `DEFAULT_CURRENCY` | Default currency code | `INR` |
| `FRONTEND_ORIGIN` | Allowed CORS origin | `http://localhost:3000` |

---

## 💻 Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Start service
uvicorn app.main:app --port 8006 --reload
```
