from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.places.model import Place
from app.modules.profiles.model import UserPost, UserVisitedPlace


class ProfileRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_visited_places(self, user_id: int) -> list[tuple[UserVisitedPlace, Place]]:
        statement = (
            select(UserVisitedPlace, Place)
            .join(Place, Place.id == UserVisitedPlace.place_id)
            .where(
                UserVisitedPlace.user_id == user_id,
                Place.deleted_at.is_(None),
                Place.latitude.is_not(None),
                Place.longitude.is_not(None),
            )
            .order_by(UserVisitedPlace.visited_at.desc(), UserVisitedPlace.created_at.desc())
        )
        return list(self.db.execute(statement).all())

    def list_posts(self, user_id: int) -> list[UserPost]:
        return list(
            self.db.scalars(
                select(UserPost)
                .where(UserPost.user_id == user_id)
                .order_by(UserPost.created_at.desc())
            )
        )

    def get_place(self, place_id: str) -> Place | None:
        return self.db.get(Place, place_id)

    def get_visited_place(self, user_id: int, place_id: str) -> UserVisitedPlace | None:
        return self.db.scalar(
            select(UserVisitedPlace).where(
                UserVisitedPlace.user_id == user_id,
                UserVisitedPlace.place_id == place_id,
            )
        )

    def add_visited_place(self, visited_place: UserVisitedPlace) -> UserVisitedPlace:
        self.db.add(visited_place)
        self.db.flush()
        return visited_place

    def commit(self) -> None:
        self.db.commit()
