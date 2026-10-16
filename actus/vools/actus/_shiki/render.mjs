// _shiki/render.mjs —— Shiki 高亮渲染器
// 用法: node render.mjs <lang> <theme> <mode:terminal|html> < input.code
import { createHighlighter } from 'shiki';
import process from 'node:process';

const args = process.argv.slice(2);
const lang = args[0] || 'python';
const theme = args[1] || 'github-dark';
const mode = args[2] || 'terminal'; // terminal | html

let code = '';
process.stdin.setEncoding('utf-8');
process.stdin.on('data', (chunk) => { code += chunk; });
process.stdin.on('end', async () => {
    try {
        const highlighter = await createHighlighter({
            themes: [theme],
            langs: [lang],
        });

        if (mode === 'html') {
            const html = highlighter.codeToHtml(code, {
                lang,
                theme,
            });
            process.stdout.write(html);
        } else {
            // 终端模式：使用 ansi 配色
            const html = highlighter.codeToHtml(code, {
                lang,
                theme,
            });
            // 简单转换：提取颜色代码，输出 ANSI
            const lines = parseHtmlToAnsi(html);
            process.stdout.write(lines);
        }
    } catch (e) {
        process.stderr.write(`shiki error: ${e.message}\n`);
        process.exit(1);
    }
});

function parseHtmlToAnsi(html) {
    // 简易 HTML → ANSI 转换
    const colorMap = {};
    const spanRegex = /<span style="color:([^"]+)">([^<]*)<\/span>/g;
    let result = '';
    let lastIndex = 0;
    let match;
    const reset = '\x1b[0m';

    // 先去掉 pre/code 标签
    let cleaned = html.replace(/<\/?pre[^>]*>/g, '').replace(/<\/?code[^>]*>/g, '');
    cleaned = cleaned.replace(/<br\s*\/?>/g, '\n').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');

    while ((match = spanRegex.exec(html)) !== null) {
        const color = match[1];
        const text = match[2].replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
        const ansiColor = hexToAnsi(color);
        result += ansiColor + text + reset;
    }

    if (!result) {
        result = cleaned;
    }
    return result;
}

function hexToAnsi(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `\x1b[38;2;${r};${g};${b}m`;
}
