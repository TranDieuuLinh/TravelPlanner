export interface VisitedPlace {
  id: string;
  placeId: string;
  name: string;
  address?: string | null;
  city?: string | null;
  country?: string | null;
  latitude: number;
  longitude: number;
  visitedAt: string;
  note?: string | null;
}

export interface ProfilePost {
  id: string;
  caption: string;
  mediaUrl: string;
  locationName?: string | null;
  createdAt: string;
}

export interface ProfileShowcase {
  visitedPlaces: VisitedPlace[];
  posts: ProfilePost[];
}
