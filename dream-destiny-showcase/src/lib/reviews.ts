import { collection, query, where, limit, getDocs } from "firebase/firestore";
import { db, isFirebaseConfigured } from "./firebase";
import { PublicReview } from "../types/review";

export interface FetchReviewsResult {
  status: "configured" | "unconfigured" | "error";
  reviews: PublicReview[];
  errorMessage?: string;
}

/**
 * Fetches verified public reviews from the dedicated Firestore public reviews collection.
 * Only queries documents where `published: true` and limits results.
 * If Firestore is not configured or in SSR/static build time, returns gracefully without throwing.
 */
export async function fetchPublicReviews(maxReviews = 6): Promise<FetchReviewsResult> {
  if (!isFirebaseConfigured || !db) {
    return {
      status: "unconfigured",
      reviews: [],
    };
  }

  try {
    const reviewsRef = collection(db, "public_reviews");
    const q = query(
      reviewsRef,
      where("published", "==", true),
      limit(maxReviews)
    );

    const snapshot = await getDocs(q);
    const reviews: PublicReview[] = [];

    snapshot.forEach((doc) => {
      const data = doc.data();
      // Ensure only approved public fields are copied
      reviews.push({
        id: doc.id,
        displayName: typeof data.displayName === "string" ? data.displayName : "Verified Traveler",
        reviewText: typeof data.reviewText === "string" ? data.reviewText : "",
        rating: typeof data.rating === "number" ? Math.min(5, Math.max(1, data.rating)) : undefined,
        tripOrDestination: typeof data.tripOrDestination === "string" ? data.tripOrDestination : undefined,
        published: true,
        createdAt: data.createdAt ? String(data.createdAt) : undefined,
      });
    });

    return {
      status: "configured",
      reviews,
    };
  } catch (error) {
    const errMessage = error instanceof Error ? error.message : "Failed to load reviews from Firestore";
    console.warn("Could not retrieve public reviews from Firestore:", errMessage);
    return {
      status: "error",
      reviews: [],
      errorMessage: errMessage,
    };
  }
}
