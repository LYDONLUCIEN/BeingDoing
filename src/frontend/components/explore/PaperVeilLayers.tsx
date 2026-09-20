/**
 * 半透明纸层 + 6px 毛玻璃背景层（样式：styles/components/openlife-paper-veil.css）
 * 用于 /explore/intro、/community、/about；与激活码页 paper 模式同一配方。
 * 纯装饰：fixed 定位、pointer-events: none，不参与阅读顺序。
 */
export default function PaperVeilLayers() {
  return (
    <div className="ol-paper-bg" aria-hidden>
      <div className="ol-paper-bg-image" />
      <div className="ol-paper-bg-veil" />
    </div>
  );
}
