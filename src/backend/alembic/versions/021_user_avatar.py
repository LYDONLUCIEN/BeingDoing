"""user avatar_url

Revision ID: 021_user_avatar
Revises: 020_coupon_expiry_and_owner
Create Date: 2026-09-17

用户头像持久化（2026-09-17 决策记录）：

背景：此前头像仅前端 URL.createObjectURL() 本地 blob 预览，从未调后端接口持久化，
且 settings/activate 两页的 /auth/me 同步 effect 用不含 avatar_url 的对象整体覆盖
Zustand store，导致「切换页面头像消失」。

存储方案（与用户确认）：
- DB users 表加 avatar_url 一列，存**后端代理 URL**：
  /api/v1/users/{user_id}/avatar?v=<上传时间戳>（永久有效，?v= 用于换头像后击穿浏览器缓存）
- 图片本体存阿里云 OSS 私有桶，确定性 key = avatars/{user_id}（无扩展名），
  重复上传同 key 覆盖，零孤儿文件，无需清理 job
- dev / prod 共用同一 bucket（soulhappy-hermes-agent，沿用现有 RAM key，不分桶）：
  两边数据库本就分离，user_id 不撞车；测试环境产生的头像垃圾图可接受
- 读取走公开代理端点 GET /users/{user_id}/avatar（CSS background 无鉴权头，必须公开），
  内容类型由 magic bytes 嗅探（png/jpeg/webp）

迁移风险：零。历史头像数据为零（功能从未持久化），无需回填。
生产部署：在生产机执行 alembic upgrade head 即可；若头像 503，
先查生产机 /etc/beingdoing.env 是否覆盖了 OSS_* 配置。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "021_user_avatar"
down_revision: Union[str, None] = "020_coupon_expiry_and_owner"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_url")
