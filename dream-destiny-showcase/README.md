# Dream Destiny Showcase Website

> **Product:** Dream Destiny — Your Travel Companion on WhatsApp  
> **Positioning:** Single-page showcase and marketing website for an AI travel planning WhatsApp bot.  
> **Architecture:** Next.js App Router (TypeScript) with Static HTML Export (`output: "export"`). No Node server, API routes, or server-side database access.

---

## Key Highlights

- **WhatsApp-First Positioning:** "No installation. No separate signup. Just WhatsApp." Prominently distinguishes the product from web planners.
- **TripForge Design Adaptation:** Built using visual guidelines and design tokens generated via **Stitch MCP** based on the TripForge Dribbble reference, balancing the pale stone background (`#F2F6F6`), sage neutral (`#B9CCCA`), near-black ink (`#0D0F10`), fresh green accents (`#79B66A`, `#B7D7AD`), and Dream Destiny's navy brand identity (`#0B2345`).
- **Official Provider Brand Mark Compliance:**
  - **ixigo:** Unaltered official rail schedule discovery mark.
  - **redBus:** Official red bus silhouette & mark.
  - **Google Flights, Google Hotels, Google Maps:** Official marks with explicit Google Maps Platform attribution notes.
  - **Amazon Bedrock:** Official AWS Architecture service mark (never retail shopping cart logo).
- **Client-Side Firestore Reviews Adapter:** Connects to public Firestore collection with strict read-only access and moderation filter (`published == true`). Gracefully handles loading, missing configuration, and empty states without inventing fake reviews.

---

## Directory Structure

```text
dream-destiny-showcase/
├── public/
│   ├── brand/
│   │   ├── dream-destiny-logo.svg       # Replaceable brand logo
│   │   └── dream-destiny-logo.png
│   ├── images/
│   │   ├── whatsapp/                    # Replaceable WhatsApp captures
│   │   │   ├── step-1-start-chat.svg
│   │   │   ├── step-2-preferences.svg
│   │   │   └── step-3-itinerary.svg
│   │   ├── journeys/                    # Destination blueprints
│   │   │   ├── udaipur.svg
│   │   │   ├── goa.svg
│   │   │   ├── munnar.svg
│   │   │   └── rishikesh.svg
│   │   └── providers/                   # Official partner logos
│   │       ├── ixigo.svg
│   │       ├── redbus.svg
│   │       ├── google-flights.svg
│   │       ├── google-hotels.svg
│   │       ├── google-maps.svg
│   │       └── amazon-bedrock.svg
│   ├── og-image.svg
│   ├── robots.txt
│   └── sitemap.xml
├── src/
│   ├── app/
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Navbar.tsx
│   │   │   └── Footer.tsx
│   │   ├── sections/
│   │   │   ├── HeroSection.tsx
│   │   │   ├── HowItWorksSection.tsx
│   │   │   ├── FeaturesSection.tsx
│   │   │   ├── PoweredBySection.tsx
│   │   │   ├── JourneysSection.tsx
│   │   │   ├── ReviewsSection.tsx
│   │   │   └── FinalCtaSection.tsx
│   │   └── ui/
│   │       ├── Button.tsx
│   │       ├── SectionHeading.tsx
│   │       ├── ScreenshotPlaceholder.tsx
│   │       ├── JourneyCard.tsx
│   │       ├── ProviderCard.tsx
│   │       ├── TestimonialCard.tsx
│   │       └── WhatsAppNoticeModal.tsx
│   ├── data/
│   │   ├── features.ts
│   │   ├── journeys.ts
│   │   └── providers.ts
│   ├── lib/
│   │   ├── firebase.ts
│   │   ├── reviews.ts
│   │   └── whatsapp.ts
│   └── types/
│       ├── journey.ts
│       ├── provider.ts
│       └── review.ts
├── .env.example
├── next.config.ts
├── package.json
└── tsconfig.json
```

---

## Environment Variables Configuration

Copy `.env.example` to `.env.local`:

```bash
cp .env.example .env.local
```

### Supported Variables:

| Variable | Description | Example |
|---|---|---|
| `NEXT_PUBLIC_WHATSAPP_NUMBER` | Bot WhatsApp phone number in international digits (no `+`, spaces, or symbols). When unset, the UI shows a helpful configuration dialog rather than broken/fake links. | `919876543210` |
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Public Firebase Web API Key for verified reviews. | `AIzaSy...` |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Firebase Auth Domain. | `your-app.firebaseapp.com` |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firebase Project ID. | `dream-destiny-prod` |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | Firebase Web App ID. | `1:123456789:web:...` |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | Firebase Messaging Sender ID. | `123456789` |
| `NEXT_PUBLIC_SITE_URL` | Canonical production site URL. | `https://dreamdestiny.ai` |

---

## Firestore Schema & Security Rules

If enabling live testimonials, create a Firestore collection named `public_reviews`.

### Expected Document Schema:
```typescript
interface PublicReviewDocument {
  displayName: string;          // e.g., "Aarav S."
  reviewText: string;           // Verified customer testimonial
  rating?: number;              // 1 to 5 integer
  tripOrDestination?: string;   // e.g., "Mumbai → Udaipur"
  published: boolean;           // MUST be true to be displayed publicly
  createdAt?: string | Timestamp;
}
```

### Firestore Security Rules (`firestore.rules`):
```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /public_reviews/{reviewId} {
      // Public clients can ONLY read reviews that are approved and published
      allow read: if resource.data.published == true;
      // All writes MUST be restricted to trusted backend/admin workflows
      allow write: if false;
    }
  }
}
```

---

## Build & Verification Commands

From `dream-destiny-showcase/`:

```bash
# Install dependencies
pnpm install

# 1. Type checking
pnpm exec tsc --noEmit

# 2. Linting
pnpm lint

# 3. Static export production build
pnpm build

# 4. Preview / Serve the static production build
pnpm serve
# or
pnpm preview
```

Static build outputs are generated in the `out/` folder, ready for deployment to any static web host, CDN, or Cloud Storage bucket (e.g. Firebase Hosting, Cloudflare Pages, AWS S3 / CloudFront, GCP Cloud Storage).
