---
aigc: true
generated-by: atomcode
generated-at: 2026-09-15T14:30:00Z
---

---
id: convert-file-to-markdown
name: Convert File to Markdown
version: 1.0.0
trust: sandbox
entry: main
description: Convert PDF/Word/PPT/Excel/image/audio files to Markdown via Microsoft MarkItDown
author: vools
platform: desktop
tags: [convert, markdown, ocr, document, office]
max_instances: 1
deprecated: false
---

# Convert File to Markdown

Convert any supported file format to Markdown using Microsoft's MarkItDown library.

## Supported Formats

| Format | Extensions | Notes |
|--------|-----------|-------|
| PDF | .pdf | Text extraction + OCR fallback |
| Word | .docx | Preserves headings, lists, tables |
| PowerPoint | .pptx | Extracts slide content |
| Excel | .xlsx | Converts sheets to Markdown tables |
| Images | .jpg, .png, .gif, .bmp, .tiff | OCR text recognition |
| Audio | .mp3, .wav, .m4a | Whisper transcription |
| HTML | .html, .htm | Strips tags, preserves structure |
| CSV | .csv | Converts to Markdown table |
| JSON | .json | Pretty-prints with syntax highlighting |
| XML | .xml | Strips tags, extracts text |
| EPub | .epub | Extracts chapter content |
| YouTube | URL | Downloads and transcribes |

## Usage

```python
from vools.actus.actions import load_action

# Load and execute the action
action = load_action("convert-file-to-markdown")
result = action.execute({
    "file_path": "report.pdf",
    "enable_ocr": True
})
print(result)  # Markdown content
```

## Input Schema

```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "输入文件路径（绝对路径或相对路径，支持 http(s) URL）"
    },
    "enable_ocr": {
      "type": "boolean",
      "default": false,
      "description": "是否启用 OCR 识别图片/PDF 中的文字"
    },
    "ocr_language": {
      "type": "string",
      "default": "eng",
      "description": "OCR 语言代码（如 eng, chi_sim, chi_tra, jpn）"
    },
    "output_path": {
      "type": "string",
      "description": "输出 Markdown 文件路径（可选，默认返回字符串）"
    },
    "enable_plugins": {
      "type": "boolean",
      "default": false,
      "description": "是否启用 MarkItDown 第三方插件"
    },
    "llm_client": {
      "type": "string",
      "description": "LLM 客户端配置（可选，用于图片描述生成）"
    },
    "timeout": {
      "type": "integer",
      "default": 120,
      "description": "转换超时时间（秒）"
    }
  },
  "required": ["file_path"]
}
```

## Dependencies

```yaml
pip:
  - markitdown[all]>=0.0.1
  - markitdown[pdf]>=0.0.1
  - markitdown[docx]>=0.0.1
  - markitdown[pptx]>=0.0.1
  - markitdown[xlsx]>=0.0.1
system:
  - tesseract-ocr          # OCR 引擎
  - tesseract-ocr-chi-sim  # 简体中文 OCR（可选）
  - tesseract-ocr-chi-tra  # 繁体中文 OCR（可选）
  - ffmpeg                 # 音频处理（可选）
env:
  - MARKITDOWN_CACHE_DIR=/tmp/markitdown
  - TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata
```

## Triggers

```yaml
- type: watch
  path: ./inbox/
  pattern: "*.{pdf,docx,pptx,xlsx}"
  debounce_ms: 2000

- type: cron
  expr: "0 9 * * 1-5"
  timezone: Asia/Shanghai
```

## Permissions

```yaml
permissions:
  - files:read
  - files:write
  - process:spawn
  - net:connect
```

## Implementation

```python
# tag: main
from pathlib import Path
from typing import Optional, Union

def convert_file_to_markdown(
    file_path: str,
    enable_ocr: bool = False,
    ocr_language: str = "eng",
    output_path: Optional[str] = None,
    enable_plugins: bool = False,
    llm_client: Optional[str] = None,
    timeout: int = 120
) -> str:
    """
    Convert a file to Markdown using Microsoft MarkItDown.

    Args:
        file_path: 输入文件路径或 URL
        enable_ocr: 是否启用 OCR
        ocr_language: OCR 语言代码
        output_path: 输出 Markdown 文件路径（可选）
        enable_plugins: 是否启用第三方插件
        llm_client: LLM 客户端配置（可选）
        timeout: 超时时间（秒）

    Returns:
        Markdown 内容字符串

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 不支持的文件格式
        TimeoutError: 转换超时
    """
    # 延迟导入，避免未安装依赖时崩溃
    try:
        from markitdown import MarkItDown
    except ImportError:
        raise ImportError(
            "markitdown is required. Install with: pip install markitdown[all]"
        )

    # 验证输入文件
    if not _validate_file(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # 初始化 MarkItDown
    md = MarkItDown(
        enable_plugins=enable_plugins,
        llm_client=llm_client
    )

    # 执行转换
    try:
        result = md.convert(file_path)
    except Exception as e:
        raise ValueError(f"Failed to convert {file_path}: {e}")

    markdown_content = result.markdown

    # 可选：写入输出文件
    if output_path:
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(markdown_content, encoding='utf-8')

    return markdown_content
```

```python
# tag: helper
def _validate_file(file_path: str) -> bool:
    """
    Validate file exists and is supported format.

    Args:
        file_path: 文件路径或 URL

    Returns:
        True if valid, False otherwise
    """
    # URL 直接返回 True
    if file_path.startswith(('http://', 'https://')):
        return True

    path = Path(file_path)
    if not path.exists():
        return False

    # 检查扩展名
    supported_extensions = {
        '.pdf', '.docx', '.pptx', '.xlsx', '.xls',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff',
        '.mp3', '.wav', '.m4a', '.ogg',
        '.html', '.htm', '.csv', '.json', '.xml', '.epub'
    }
    return path.suffix.lower() in supported_extensions


def _get_file_info(file_path: str) -> dict:
    """
    Get file information for logging.

    Args:
        file_path: 文件路径

    Returns:
        File info dict
    """
    path = Path(file_path)
    return {
        'name': path.name,
        'extension': path.suffix.lower(),
        'size': path.stat().st_size if path.exists() else 0,
        'is_url': file_path.startswith(('http://', 'https://'))
    }
```

```python
# tag: cli
if __name__ == '__main__':
    import argparse
    import sys

    parser = argparse.ArgumentParser(description='Convert files to Markdown')
    parser.add_argument('file', help='Input file path or URL')
    parser.add_argument('-o', '--output', help='Output Markdown file path')
    parser.add_argument('--ocr', action='store_true', help='Enable OCR')
    parser.add_argument('--lang', default='eng', help='OCR language')
    parser.add_argument('--timeout', type=int, default=120, help='Timeout in seconds')

    args = parser.parse_args()

    try:
        result = convert_file_to_markdown(
            file_path=args.file,
            enable_ocr=args.ocr,
            ocr_language=args.lang,
            output_path=args.output,
            timeout=args.timeout
        )
        if not args.output:
            print(result)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```

## Notes

- **首次使用**: 需要安装 `pip install markitdown[all]`
- **OCR 依赖**: 需要安装 tesseract-ocr 系统包
- **音频转写**: 需要安装 whisper 和 ffmpeg
- **性能**: 大文件（>50MB）建议增加 timeout
- **URL 支持**: 直接传入 YouTube 链接可自动下载并转录
- **LLM 增强**: 传入 llm_client 可生成图片描述
