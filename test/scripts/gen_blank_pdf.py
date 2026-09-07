# 临时脚本：生成纯净空白版报告 PDF（无任何文字，仅空白页）
# 用法：src/backend/venv/bin/python test/scripts/gen_blank_pdf.py [页数] [输出路径]
import sys
from pathlib import Path

PAGES = int(sys.argv[1]) if len(sys.argv) > 1 else 1
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent.parent / "reports" / "blank_report.pdf"

from weasyprint import HTML

# 用分页符生成 N 页空白 A4，无任何文本内容
html = "<html><body>" + "".join('<div style="page-break-after: always;"></div>' for _ in range(max(PAGES - 1, 0))) + "<div></div></body></html>"

OUT.parent.mkdir(parents=True, exist_ok=True)
HTML(string=html).write_pdf(str(OUT))
print(f"已生成：{OUT}（{PAGES} 页空白 A4）")
