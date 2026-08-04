export type TravelGroup = {
  id: number;
  countryCode: string;
  countryName: string;
  name: string;
  photoUrl: string;
  memberCount: number;
  isMember: boolean;
  isPublic: boolean;
};

export type TravelGroupList = {
  items: TravelGroup[];
  total: number;
};

export type TravelGroupMembership = {
  groupId: number;
  isMember: boolean;
  memberCount: number;
};

export type TravelGroupPostAuthor = {
  id: number;
  fullName: string;
  avatarUrl: string | null;
};

export type TravelGroupPost = {
  id: string;
  content: string;
  createdAt: string;
  author: TravelGroupPostAuthor;
};

export type TravelGroupDetail = {
  group: TravelGroup;
  posts: TravelGroupPost[];
  totalPosts: number;
};
