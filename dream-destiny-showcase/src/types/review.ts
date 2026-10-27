export interface PublicReview {
  id: string;
  displayName: string;
  reviewText: string;
  rating?: number;
  tripOrDestination?: string;
  published: boolean;
  createdAt?: string;
}
