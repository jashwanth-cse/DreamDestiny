# Hotel recommendation in a new itinerary

The planner collects dated Google Hotels search results through SerpApi. After Bedrock schedules attractions, the planner selects the hotel itself from those results. This fills the hotel even when Bedrock returns `hotel: null`, and removes any hotel that was not in the provider response.

The selector considers hotels with INR rates first. It applies the WhatsApp budget level as a nightly ceiling: low ₹1,500, medium ₹5,000, high unrestricted. A stricter hotel category ceiling also applies. If no sourced hotel meets the target, it may show the best sourced option with an explicit over-budget warning. A missing rate is displayed as unverified, never estimated.

For the selected itinerary attractions, it preselects at most ten geographically plausible hotels, then asks Google Routes for driving times to at most twenty attractions (200 matrix elements maximum). Each attraction has equal weight. The score combines average drive time, a penalty for the furthest attraction, a Bayesian review rating (40-review prior), and nightly price. This favors a hotel with balanced access to the whole itinerary over one beside just one attraction. The WhatsApp message shows the price, reviews, average and worst road time where available. Times use `TRAFFIC_UNAWARE` routing and are estimates, not live traffic or room availability. If Routes is unavailable, the choice falls back to sourced reviews and price and says that road times could not be verified.

For train arrivals, the selected train's destination station is used. For buses, a uniquely matched provider dropping point is used; an ambiguous or city-only stop is not treated as a precise location. Google Geocoding resolves the stop and a one-element Routes query estimates the drive to the hotel. The itinerary and WhatsApp message include a taxi/auto instruction and Google Maps directions. If the exact stop or route cannot be established, the message asks the traveler to confirm it or check live travel time; it does not invent a duration.

## Configuration and testing

Set `SERPAPI_API_KEY` for the hotel-service and `GOOGLE_MAPS_API_KEY` for the planner-service. Enable the Google Routes API and Geocoding API on the Maps key. The existing `BEDROCK_API_KEY` and service URLs remain required for the full planner. See the root `.env.example` and deployment documentation for the rest.

From each service directory, run `python -m pytest tests -q` in `planner-service` and `whatsapp-bot-service`. For a manual WhatsApp check, create a new train or bus trip, choose a low or medium budget, and inspect the itinerary's **HOTEL & STAY** and **AFTER ARRIVING IN THE CITY** sections. Repeat with a different budget; check that the hotel rate and review count are present, the hotel is from SerpApi, and the transfer names the actual arrival station or drop point. Supplier rates, room availability, and traffic can change before booking.
