/**
 * HTML 转 PDF 导出脚本
 * 使用 Playwright 实现高质量的 PDF 导出，完美保留网页样式
 *
 * 使用方法：
 * 1. 安装依赖：npm install playwright
 * 2. 运行脚本：node export-pdf.js
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

// 配置参数
const CONFIG = {
    // HTML 文件路径（相对于当前脚本）
    htmlPath: path.join(__dirname, 'index2.html'),

    // 输出 PDF 文件名
    outputPdf: 'KATE优势身份证_完整报告.pdf',

    // 页面格式选项
    format: {
        // 纸张格式: 'A4', 'Letter' 等，或自定义尺寸 {width: number, height: number}
        size: 'A4',

        // 页边距 (单位: px, in, cm, mm)
        margins: {
            top: '0.5cm',
            right: '0.5cm',
            bottom: '0.5cm',
            left: '0.5cm'
        },

        // 是否打印背景图形（渐变、背景色等）
        printBackground: true,

        // 页面方向: 'portrait' (纵向) 或 'landscape' (横向)
        orientation: 'portrait'
    },

    // 浏览器视口大小（影响页面渲染）
    viewport: {
        width: 1200,
        height: 1600
    },

    // 等待时间（毫秒），确保页面完全加载
    waitTime: 2000,

    // 是否显示页眉页脚
    displayHeaderFooter: false,

    // 是否在无头模式下运行（不显示浏览器窗口）
    headless: true
};

/**
 * 将 HTML 文件转换为 PDF
 */
async function htmlToPdf() {
    console.log('🚀 开始导出 PDF...\n');

    let browser = null;

    try {
        // 检查 HTML 文件是否存在
        if (!fs.existsSync(CONFIG.htmlPath)) {
            throw new Error(`HTML 文件不存在: ${CONFIG.htmlPath}`);
        }

        // 启动浏览器
        console.log('📦 启动浏览器...');
        browser = await chromium.launch({
            headless: CONFIG.headless,
        });

        const context = await browser.newContext({
            viewport: CONFIG.viewport,
        });

        const page = await context.newPage();

        // 加载 HTML 文件
        const fileUrl = `file://${CONFIG.htmlPath}`;
        console.log(`📄 加载 HTML 文件: ${CONFIG.htmlPath}`);
        await page.goto(fileUrl, {
            waitUntil: 'networkidle',
            timeout: 30000
        });

        // 等待页面完全渲染
        console.log(`⏳ 等待页面渲染 (${CONFIG.waitTime}ms)...`);
        await page.waitForTimeout(CONFIG.waitTime);

        // 等待字体加载完成
        await page.mainFrame().waitForFunction(() => {
            return document.fonts.ready.then(() => true);
        }).catch(() => {
            console.log('⚠️  字体加载超时，继续导出...');
        });

        // 生成 PDF
        console.log('📝 生成 PDF...');
        const pdfBuffer = await page.pdf({
            format: CONFIG.format.size,
            margin: CONFIG.format.margins,
            printBackground: CONFIG.format.printBackground,
            landscape: CONFIG.format.orientation === 'landscape',
            displayHeaderFooter: CONFIG.displayHeaderFooter,
            preferCSSPageSize: false,
        });

        // 保存 PDF 文件
        const outputPath = path.join(__dirname, CONFIG.outputPdf);
        fs.writeFileSync(outputPath, pdfBuffer);

        console.log(`\n✅ PDF 导出成功!`);
        console.log(`📁 保存位置: ${outputPath}`);
        console.log(`📊 文件大小: ${(pdfBuffer.length / 1024 / 1024).toFixed(2)} MB`);

    } catch (error) {
        console.error('\n❌ 导出失败:', error.message);
        console.error(error.stack);
        process.exit(1);
    } finally {
        // 关闭浏览器
        if (browser) {
            await browser.close();
            console.log('\n👋 浏览器已关闭');
        }
    }
}

/**
 * 批量导出多种格式
 */
async function exportMultipleFormats() {
    const formats = [
        { name: 'A4纵向', size: 'A4', orientation: 'portrait' },
        { name: 'A4横向', size: 'A4', orientation: 'landscape' },
        { name: 'Letter纵向', size: 'Letter', orientation: 'portrait' },
    ];

    console.log('🚀 开始批量导出...\n');

    let browser = null;

    try {
        if (!fs.existsSync(CONFIG.htmlPath)) {
            throw new Error(`HTML 文件不存在: ${CONFIG.htmlPath}`);
        }

        console.log('📦 启动浏览器...');
        browser = await chromium.launch({
            headless: CONFIG.headless,
        });

        const context = await browser.newContext({
            viewport: CONFIG.viewport,
        });

        const fileUrl = `file://${CONFIG.htmlPath}`;

        for (const format of formats) {
            try {
                console.log(`\n📄 导出 ${format.name}...`);

                const page = await context.newPage();
                await page.goto(fileUrl, {
                    waitUntil: 'networkidle',
                    timeout: 30000
                });

                await page.waitForTimeout(CONFIG.waitTime);

                const filename = `KATE优势身份证_${format.name}.pdf`;
                const outputPath = path.join(__dirname, filename);

                const pdfBuffer = await page.pdf({
                    format: format.size,
                    margin: CONFIG.format.margins,
                    printBackground: CONFIG.format.printBackground,
                    landscape: format.orientation === 'landscape',
                    displayHeaderFooter: CONFIG.displayHeaderFooter,
                    preferCSSPageSize: false,
                });

                fs.writeFileSync(outputPath, pdfBuffer);
                console.log(`✅ ${format.name} 导出成功: ${filename}`);

                await page.close();
            } catch (error) {
                console.error(`❌ ${format.name} 导出失败:`, error.message);
            }
        }

        console.log('\n✅ 批量导出完成!');

    } catch (error) {
        console.error('\n❌ 批量导出失败:', error.message);
        process.exit(1);
    } finally {
        if (browser) {
            await browser.close();
        }
    }
}

// 主程序
if (require.main === module) {
    const args = process.argv.slice(2);

    if (args.includes('--batch') || args.includes('-b')) {
        // 批量导出模式
        exportMultipleFormats();
    } else if (args.includes('--help') || args.includes('-h')) {
        // 显示帮助信息
        console.log(`
HTML 转 PDF 导出工具
===================

使用方法:
  node export-pdf.js              # 导出默认格式 (A4纵向)
  node export-pdf.js --batch      # 批量导出多种格式
  node export-pdf.js --help       # 显示帮助信息

配置说明:
  编辑脚本顶部的 CONFIG 对象来自定义导出参数

注意事项:
  - 首次运行会自动下载浏览器，需要等待一段时间
  - 确保已安装 Node.js 环境
  - HTML 文件必须与脚本在同一目录
        `);
    } else {
        // 默认导出单个文件
        htmlToPdf();
    }
}

module.exports = { htmlToPdf, exportMultipleFormats };
