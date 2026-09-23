# 0923 完成：首页用户头像替换 + 报告扇形构图上移

## 一、用户评价头像替换（5 人）

新素材位于 `wiki/开发文档/0923/`，按名字替换进 3×3 雪碧图 `testimonial-avatars.png`（1254×1254，格 418×418）：

| 姓名 | 格位 (background-position) | 处理方式 |
|---|---|---|
| 小林 | 0% 0% | 整图放入（头肩照居中） |
| Maggie | 50% 0% | 整图放入（深蓝影棚半身侧脸） |
| 阿文 | 100% 0% | **最小裁切成正方形**（506×395 → 395×395 居中横裁，不放大） |
| 晓敏 | 0% 50% | 整图放入（185×185 放大到 418，webp 端又缩回 168，几乎无损） |
| 老K | 50% 50% | 整图放入（黑白抽象纸卷艺术照——已与需求方确认故意为之） |

其余 4 人（苏苏/浩然/小雨/阿杰）未动。重新导出：
- `public/assets/openlife-journey/testimonial-avatars.png`（源图）
- `public/assets/openlife-journey/testimonial-avatars.webp`（504×504, q85, 41KB）
- CSS 缓存参数 `?v=20260921` → `?v=20260923`（openlife-reference-home.css）

## 二、报告扇形整体上移 ~35px

问题：收拢成扇形最终态时侧页底边下沉（页底 48px + side-y +10px + 旋转轴 94% 外扩），视觉中心太靠下。

改动：
1. `openlife-reference-home.css` `.ol-report-page` `bottom: 48px → 30px`
2. `openlife-reference-home.css` `.ol-report-fan::after`（地面阴影）`bottom: 22px → 12px` 跟随上移
3. `app/(main)/page.tsx` `--report-side-y` 最终值 `+10px → -6px`（收拢时侧页不再下沉、微升）
4. **移动端补丁**：≤720px 断点里 `.ol-report-page { bottom: 38px }` 覆盖了桌面值（首测移动端未生效的原因），改为 `20px`

## 验证

- 雪碧图 9 格逐格视觉复核：新 5 格就位、旧 4 格未动
- 桌面 1440px progress=1 截图：顶距 ~110px / 底距 ~70px，视觉重心回正且保留扇形沉稳感
- 移动 390px progress=1 截图：垂直居中确认，左右页边距 ~10px 无裁切
- `next lint` 通过（仅页面既有 `<img>` 警告）

## 备注

- 报告预览三张 webp 素材本身偏模糊，需求方说明后续会更换素材，本次未动
- 头像裁剪策略经确认：方形照片整图放入"尽可能呈现"；阿文按"自动剪裁最小比例成为正方形"处理
