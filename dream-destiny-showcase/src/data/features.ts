export interface FeatureItem {
  id: string;
  title: string;
  tagline: string;
  description: string;
  disclaimer?: string;
  icon: string;
  accentColor?: string;
}

export const featuresData: FeatureItem[] = [
  {
    id: "ai-itineraries",
    title: "AI-Powered Itineraries",
    tagline: "Structured day-by-day plans",
    description: "Converts your destination preferences, trip duration, and pace into structured, logical daily schedules directly in WhatsApp.",
    disclaimer: "Itineraries are AI-assisted guides; schedules and attraction hours should be confirmed locally.",
    icon: "sparkles",
    accentColor: "green",
  },
  {
    id: "multi-mode-travel",
    title: "Multi-Mode Travel Discovery",
    tagline: "Trains, buses, and flights",
    description: "Compare transit possibilities across rail schedules, intercity bus options, and air routes where route data is available.",
    disclaimer: "Seat availability, fares, and running status depend on provider endpoints and may fluctuate.",
    icon: "route",
    accentColor: "navy",
  },
  {
    id: "stay-suggestions",
    title: "Stay Suggestions",
    tagline: "Curated accommodation ideas",
    description: "Discover verified lodging suggestions, neighborhood proximity, and estimated rate indicators where data is returned.",
    disclaimer: "Dream Destiny showcases available stay data; bookings and payments are finalized with official booking partners.",
    icon: "hotel",
    accentColor: "sage",
  },
  {
    id: "places-to-explore",
    title: "Places Worth Exploring",
    tagline: "Attractions & cultural spots",
    description: "Discover notable landmarks, cultural attractions, viewpoints, and local activities tailored to your journey's focus.",
    disclaimer: "Opening hours, entry fees, and seasonal availability are subject to local management.",
    icon: "compass",
    accentColor: "green",
  },
  {
    id: "one-familiar-chat",
    title: "One Familiar Chat",
    tagline: "No new apps or logins",
    description: "Plan your entire trip inside WhatsApp. No app store downloads, no account setup, and no complex multi-tab planner screens.",
    disclaimer: "Requires standard WhatsApp connectivity.",
    icon: "message-circle",
    accentColor: "green",
  },
  {
    id: "practical-trip-context",
    title: "Practical Trip Context",
    tagline: "Essential journey logistics",
    description: "Receive organized departure checkpoints, suggested travel windows, and cohesive route summaries in easy-to-read chat messages.",
    disclaimer: "Travelers should check official advisories and transit guidelines before departure.",
    icon: "map-pin",
    accentColor: "navy",
  },
];
