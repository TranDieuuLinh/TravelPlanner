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
  contentType: "post" | "reel";
  caption: string;
  mediaUrl: string;
  locationName: string;
  createdAt: string;
}

export interface ExplorePost extends ProfilePost {
  authorName: string;
  authorAvatarUrl?: string | null;
}

export interface ProfileShowcase {
  visitedPlaces: VisitedPlace[];
  posts: ProfilePost[];
}
