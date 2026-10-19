from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ArticleTag(Base):
    """文章与标签的多对多关联表。

    业务上没有独立语义，但写成 declarative 类是为了与其余模型
    保持同一套 Mapped / mapped_column 定义风格，也便于将来扩展。
    """

    __tablename__ = "article_tags"

    article_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )