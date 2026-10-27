export interface Journey {
  id: string;
  slug: string;
  title: string;
  destination: string;
  stateOrRegion: string;
  country: string;
  description: string;
  tags: string[];
  duration: string;
  idealFor: string;
  sampleItinerarySnippet: string;
  image: string;
  imageAlt: string;
}
