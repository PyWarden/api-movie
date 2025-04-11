from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Boolean,
    Table,
    Float,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .db import Base
import secrets
from datetime import datetime

# Связующие таблицы
movie_actors = Table(
    "movie_actors",
    Base.metadata,
    Column("movie_id", Integer, ForeignKey("movies.id")),
    Column("actor_id", Integer, ForeignKey("actors.id")),
)

movie_directors = Table(
    "movie_directors",
    Base.metadata,
    Column("movie_id", Integer, ForeignKey("movies.id")),
    Column("director_id", Integer, ForeignKey("directors.id")),
)

movie_genres = Table(
    "movie_genres",
    Base.metadata,
    Column("movie_id", Integer, ForeignKey("movies.id")),
    Column("genre_id", Integer, ForeignKey("genres.id")),
)

movie_countries = Table(
    "movie_countries",
    Base.metadata,
    Column("movie_id", Integer, ForeignKey("movies.id")),
    Column("country_id", Integer, ForeignKey("countries.id")),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    api_key = Column(
        String,
        unique=True,
        index=True,
        nullable=False,
        default=lambda: secrets.token_urlsafe(32),
    )
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Переименовываем для соответствия фактическому использованию
    daily_request_limit = Column(Integer, default=1000)
    requests_count = Column(Integer, default=0)
    last_request_reset = Column(DateTime(timezone=True), server_default=func.now())

    requests = relationship("APIRequest", back_populates="user")


class APIRequest(Base):
    __tablename__ = "api_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    endpoint = Column(String)
    method = Column(String)
    status_code = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="requests")


class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    original_title = Column(String)
    description = Column(String)
    year = Column(Integer)
    rating = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    actors = relationship("Actor", secondary=movie_actors, back_populates="movies")
    directors = relationship(
        "Director", secondary=movie_directors, back_populates="movies"
    )
    genres = relationship("Genre", secondary=movie_genres, back_populates="movies")
    countries = relationship(
        "Country", secondary=movie_countries, back_populates="movies"
    )


class Actor(Base):
    __tablename__ = "actors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    movies = relationship("Movie", secondary=movie_actors, back_populates="actors")


class Director(Base):
    __tablename__ = "directors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    movies = relationship(
        "Movie", secondary=movie_directors, back_populates="directors"
    )


class Genre(Base):
    __tablename__ = "genres"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    movies = relationship("Movie", secondary=movie_genres, back_populates="genres")


class Country(Base):
    __tablename__ = "countries"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    movies = relationship(
        "Movie", secondary=movie_countries, back_populates="countries"
    )  # Исправлено здесь
