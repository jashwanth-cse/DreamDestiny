Implement a production-ready, scalable railway station lookup and train-route fallback system using the existing railway_stations.json dataset.

Goal:
1. Make station-name → station-code lookup extremely fast using the local JSON.
2. When no direct train is returned for the requested source → destination, automatically generate verified fallback routes using railway division and state-capital mappings.

Requirements:

## 1. High-performance station lookup

Use:
data/railway_stations.json

Load the dataset ONCE at application startup.

Build in-memory indexes:

- normalized_name → station record(s)
- station_code → station record
- division → stations
- state → stations

Do NOT scan the JSON list for every request.

Normalization must be deterministic:
- lowercase
- trim whitespace
- collapse repeated spaces
- normalize punctuation
- support configured aliases
- preserve station-code accuracy

Lookup priority:

1. exact normalized-name lookup
2. configured alias lookup
3. deterministic fuzzy match only when confidence is above a strict threshold
4. ambiguous/unknown result

Never arbitrarily select between multiple matching stations.

Return a structured result containing at least:
- station_name
- station_code
- division
- state
- district
- match_type
- confidence

The resolver must be independent from the external train API.

## 2. Train search fallback strategy

Keep the existing train-search source/API unchanged.

For:
source → destination

First resolve both stations locally and search the existing train source normally.

IMPORTANT:
Only trigger fallback when the train source explicitly returns NO DIRECT TRAINS.
Do not trigger fallback because of an API error, timeout, malformed response, or temporary failure.

Fallback hierarchy:

LEVEL 1 — Direct route
source → destination

If trains exist:
    return the original results.

LEVEL 2 — Division fallback

Find the source station's division and destination station's division from railway_stations.json.

Find a configured representative/hub station for each division.

Example:
Rajapalayam
→ division: Madurai
→ division hub: Madurai (MDU)

Delhi
→ corresponding division
→ division hub

Search:

Madurai → Delhi

Do NOT assume that the division name itself is always a valid station.
Use an explicit division-hub mapping/configuration generated or validated from the station dataset.

If a valid direct train exists:
return the fallback route with metadata explaining:

original_source
original_destination
fallback_level = "division"
fallback_source
fallback_destination
reason

If no train exists, continue.

LEVEL 3 — State-capital fallback

Create:

data/state_capitals.json

Structure:

{
  "Tamil Nadu": {
    "capital": "Chennai",
    "station_code": "MAS"
  },
  ...
}

Include all Indian states and union territories for which a valid capital railway station can be determined.

Do NOT blindly assume the capital city name equals the railway station name/code.
Use the railway station dataset to resolve the capital station and keep the mapping configurable.

For the original source and destination:

source station
→ source state
→ state-capital station

destination station
→ destination state
→ state-capital station

Example:

Rajapalayam
→ Tamil Nadu
→ Chennai (MAS)

Delhi
→ Delhi
→ New Delhi / configured capital station

Then search:

MAS → destination-capital-code

If a valid train exists, return it as a state-capital fallback.

Again, verify the route through the existing train source.
Never claim that a route exists without source confirmation.

## 3. Fallback response model

Add structured metadata:

{
  "route_type": "direct | division_fallback | state_capital_fallback",
  "original_source": {...},
  "original_destination": {...},
  "actual_source": {...},
  "actual_destination": {...},
  "fallback_reason": "...",
  "trains": [...]
}

The frontend must be able to clearly show that the returned train is NOT a direct train from the user's original station.

## 4. Prevent unnecessary API calls

Optimize the flow:

- Local station resolution must require zero external API calls.
- Cache station indexes in memory.
- Cache normalized station resolutions where useful.
- Do not repeatedly resolve the same station during one request.
- Do not perform fallback searches until the previous search has explicitly returned zero trains.
- Do not call the same route twice.
- Deduplicate fallback routes before searching.

Use async/concurrent calls only when routes are independent.

## 5. Accuracy rules

Never:
- invent station codes
- invent division hubs
- invent capital station codes
- assume a train exists
- silently replace the user's requested stations
- return a fallback as if it were a direct route

Every station code must originate from:
- railway_stations.json
- configured alias/division/state-capital mapping
- existing verified train API response

If a division hub or capital station cannot be resolved confidently:
skip that fallback and continue to the next valid strategy.

If no verified fallback exists:
return a structured "no_route_found" result.

## 6. Data generation

Create:

data/state_capitals.json

Create a one-time preprocessing/validation script that:

- reads railway_stations.json
- validates capital-city station mappings
- validates station codes
- detects missing capitals
- detects duplicate/ambiguous mappings
- generates the final compact JSON
- produces a validation report

Keep all mappings configurable so they can be corrected without modifying application logic.

## 7. Architecture

Keep responsibilities separated:

RailwayStationResolver
    → local station lookup

DivisionResolver
    → station → division → configured division hub

StateCapitalResolver
    → state → capital station

TrainSearchService
    → existing external train source

RouteFallbackService
    → direct → division → state-capital fallback orchestration

Do NOT put this logic inside the API route/controller.

Do NOT use an LLM for station resolution or fallback selection.

## 8. Testing

Add tests for:

- exact station lookup
- normalized station lookup
- aliases
- duplicate station names
- ambiguous stations
- unknown station
- station → division resolution
- division → hub resolution
- station → state resolution
- state → capital station resolution
- direct train available
- no direct train → division fallback
- division fallback unavailable → state-capital fallback
- no fallback available
- train API error must NOT trigger fallback
- duplicate route prevention
- correct fallback metadata

Run all existing railway/transport tests and verify existing behavior remains compatible.

## 9. Performance

Measure and log:

- station lookup latency
- train API latency
- number of fallback searches
- fallback level used
- total route-resolution latency

The railway dataset must never be parsed from PDF or scanned from disk at request time.

Target architecture:

PDF
 ↓
railway_stations.json
 ↓
startup indexing
 ↓
RailwayStationResolver
 ↓
Direct train search
 ↓ no trains
DivisionFallback
 ↓ no trains
StateCapitalFallback
 ↓
Verified train results / no_route_found