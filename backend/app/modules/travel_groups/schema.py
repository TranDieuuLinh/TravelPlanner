from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TravelGroupResponse(BaseModel):
    id: int
    country_code: str = Field(alias="countryCode")
    country_name: str = Field(alias="countryName")
    name: str
    photo_url: str = Field(alias="photoUrl")
    member_count: int = Field(alias="memberCount")
    is_member: bool = Field(alias="isMember")
    is_public: bool = Field(alias="isPublic")

    model_config = ConfigDict(populate_by_name=True)


class TravelGroupListResponse(BaseModel):
    items: list[TravelGroupResponse]
    total: int


class TravelGroupMembershipResponse(BaseModel):
    group_id: int = Field(alias="groupId")
    is_member: bool = Field(alias="isMember")
    member_count: int = Field(alias="memberCount")

    model_config = ConfigDict(populate_by_name=True)


class TravelGroupPostCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class TravelGroupPostAuthorResponse(BaseModel):
    id: int
    full_name: str = Field(alias="fullName")
    avatar_url: str | None = Field(default=None, alias="avatarUrl")

    model_config = ConfigDict(populate_by_name=True)


class TravelGroupPostResponse(BaseModel):
    id: str
    content: str
    created_at: datetime = Field(alias="createdAt")
    author: TravelGroupPostAuthorResponse

    model_config = ConfigDict(populate_by_name=True)


class TravelGroupDetailResponse(BaseModel):
    group: TravelGroupResponse
    posts: list[TravelGroupPostResponse]
    total_posts: int = Field(alias="totalPosts")

    model_config = ConfigDict(populate_by_name=True)
