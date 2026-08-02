import { apiFetch } from "@/lib/api";
import type {
  TravelGroupDetail,
  TravelGroupList,
  TravelGroupMembership,
  TravelGroupPost,
} from "@/types/travel-groups";

export function getTravelGroups() {
  return apiFetch<TravelGroupList>("/travel-groups");
}

export function joinTravelGroup(groupId: number) {
  return apiFetch<TravelGroupMembership>(`/travel-groups/${groupId}/membership`, {
    method: "PUT",
  });
}

export function getTravelGroup(groupId: number) {
  return apiFetch<TravelGroupDetail>(`/travel-groups/${groupId}`);
}

export function createTravelGroupPost(groupId: number, content: string) {
  return apiFetch<TravelGroupPost>(`/travel-groups/${groupId}/posts`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}
