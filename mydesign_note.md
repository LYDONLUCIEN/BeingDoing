
1. 配置文件（你可直接编辑）
src/frontend/config/design-effects.json
已包含 5 个预设：
ID	名称	说明
none	无（使用主题默认）	关闭效果
glass	毛玻璃	半透明卡片 + 模糊
glass-strong	毛玻璃（强）	更强的模糊
paper	素描纸	暖色背景 + 纹理
flat	扁平	实色、无模糊
在 presets 中新增或修改对象即可扩展预设。
src/frontend/config/design-effects.json


相关文件
文件	用途
config/design-effects.json	预设配置
stores/designEffectsStore.ts	效果 Store
components/layout/DesignEffectsInjector.tsx	注入效果
styles/base/design-effects.css	效果相关样式
app/(main)/settings/style-lab/page.tsx	效果实验室页面
docs/DESIGN_EFFECTS.md	使用说明