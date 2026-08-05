from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.place_repository import (
    KnowledgeGraphPlaceRecord,
    KnowledgeGraphPlaceRepository,
)
from app.modules.profiles.model import UserPost, UserVisitedPlace
from app.modules.users.model import User


class ProfileRepository:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.places = KnowledgeGraphPlaceRepository(db)

    def list_visited_places(
        self, user_id: int
    ) -> list[tuple[UserVisitedPlace, KnowledgeGraphPlaceRecord]]:
        visits = list(
            self.db.scalars(
                select(UserVisitedPlace)
                .where(
                    UserVisitedPlace.user_id == user_id,
                    UserVisitedPlace.entity_id.is_not(None),
                )
            .order_by(UserVisitedPlace.visited_at.desc(), UserVisitedPlace.created_at.desc())
            )
        )
        result: list[tuple[UserVisitedPlace, KnowledgeGraphPlaceRecord]] = []
        for visit in visits:
            place = self.places.get(visit.entity_id or "")
            if place and place.latitude is not None and place.longitude is not None:
                result.append((visit, place))
        return result

    def list_posts(self, user_id: int) -> list[UserPost]:
        return list(
            self.db.scalars(
                select(UserPost)
                .where(UserPost.user_id == user_id)
                .order_by(UserPost.created_at.desc())
            )
        )

    def list_public_posts(self, *, limit: int, offset: int) -> list[tuple[UserPost, User]]:
        statement = (
            select(UserPost, User)
            .join(User, User.id == UserPost.user_id)
            .where(User.status == "active")
            .order_by(UserPost.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.execute(statement).all())

    def get_place(self, entity_id: str) -> KnowledgeGraphPlaceRecord | None:
        return self.places.get(entity_id)

    def get_visited_place(self, user_id: int, place_id: str) -> UserVisitedPlace | None:
        return self.db.scalar(
            select(UserVisitedPlace).where(
                UserVisitedPlace.user_id == user_id,
                UserVisitedPlace.entity_id == place_id,
            )
        )

    def add_visited_place(self, visited_place: UserVisitedPlace) -> UserVisitedPlace:
        self.db.add(visited_place)
        self.db.flush()
        return visited_place

    def add_post(self, post: UserPost) -> UserPost:
        self.db.add(post)
        self.db.flush()
        return post

    def commit(self) -> None:
        self.db.commit()
