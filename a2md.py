import os
import sys
import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from readability import Document  # pip install readability-lxml
from playwright.sync_api import sync_playwright
from urllib.parse import unquote
from urllib.parse import urlparse
def get_html(url, use_playwright=False):
    """获取 HTML，支持 requests 和 playwright"""
    if use_playwright:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(url, timeout=60000)
            page.wait_for_timeout(5000)  # 等待 5 秒加载
            html = page.locator('div[role="textbox"]').first.inner_html()
            title = page.locator('div[role="textbox"]').first.locator('h1').first.inner_text()
            browser.close()
            return [html, title]
    else:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        return [r.text, None]

def clean_html(html):
    """清理 emoji、无用标签"""
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src and img.get("srcset"):
            src = img.get("srcset").split(" ")[0]
        if src:
            img["src"] = src
        else:
            img.decompose()
    return str(soup)

def extract_title(doc, fallback="untitled"):
    """优先用 meta-title，没有就用 h1，再 fallback"""
    if doc.title():
        return doc.title().strip()[:80]
    return fallback

import os
import re
import requests
from urllib.parse import unquote

def process_images(md_text: str, article_id: str, output_dir: str, folder_path: str) -> str:
    """
    下载 markdown 中的所有图片到本地，并替换为本地相对路径
    :param md_text: 原始 markdown
    :param article_id: 文章 id，用于区分不同文章的图片目录
    :param output_dir: 分类目录，比如 web3
    :param folder_path: 本地保存 md 文件的目录
    :return: 替换后的 markdown
    """
    # 匹配 markdown 图片语法: ![](...)
    pattern = re.compile(r'!\[[^\]]*\]\((.*?)\)')

    # 图片存储目录：./source/_posts/<article_id>
    img_dir = os.path.join(folder_path)
    os.makedirs(img_dir, exist_ok=True)

    img_count = 0

    def download_and_replace(match):
        nonlocal img_count
        img_count += 1

        img_url = match.group(1)

        # 处理 notion 的 /image/ 链接
        if img_url.startswith("/image/"):
            img_url_full = "https://www.notion.so" + img_url
        else:
            img_url_full = img_url

        # 提取文件扩展名
        filename_raw = unquote(img_url.split("/")[-1].split("?")[0])
        ext = os.path.splitext(filename_raw)[1] or ".jpg"
        filename = f"{img_count}{ext}"  # 避免重名覆盖

        local_path = os.path.join(img_dir, filename)

        # 下载图片
        try:
            if not os.path.exists(local_path):
                r = requests.get(img_url_full, timeout=15)
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(r.content)
                # print(f"✅ 下载成功: {img_url_full} -> {local_path}")
            else:
                print(f"ℹ️ 已存在跳过: {local_path}")
        except Exception as e:
            print(f"❌ 下载失败: {img_url_full}, 错误: {e}")
            return match.group(0)  # 保留原始链接

        # 相对路径: category/article_id/filename
        rel_path = f"{output_dir}/{article_id}/{filename}"
        return f"![]({rel_path})"

    return pattern.sub(download_and_replace, md_text)

def extract_article_id(url: str) -> str:
    """
    根据文章链接生成 article_id
    优先取最后一段 path，如果为空则用域名
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")  # 去掉末尾 /
    
    if path:
        article_id = path.split("/")[-1]
    else:
        article_id = parsed.netloc
    
    # 去掉参数和锚点
    article_id = article_id.split("?")[0].split("#")[0]

    # 清理非法字符
    article_id = re.sub(r'\W+', '_', article_id)
    
    return article_id or "article"

def download_article(url, category="web3"):
    """通用文章转 Markdown，支持 Notion/Medium/Mirror"""
    use_playwright = ("notion.so" in url) or ("notion.site" in url)

    try:
        html = get_html(url, use_playwright=use_playwright)[0]
        notion_title = get_html(url, use_playwright=use_playwright)[1]
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return

    doc = Document(html)
    
    if use_playwright:
        content_html = clean_html(html) 
        title = notion_title
    else:
        content_html = clean_html(doc.summary())
        title = extract_title(doc, fallback="untitled")

        
    markdown = md(content_html, heading_style="ATX", strip=["svg", "style"])
    
    article_id = extract_article_id(url)
    base_path = "./source/_posts"
    folder_path = os.path.join(base_path, article_id)
    os.makedirs(folder_path, exist_ok=True)
    md_path = os.path.join(base_path, f"{article_id}.md")

    markdown = process_images(markdown, article_id, output_dir=category, folder_path=folder_path)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(f"title: {title}\n")
        f.write(f"date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("categories:\n")
        f.write(f"  - {category}\n")
        f.write("tags:\n")
        f.write("  - 转载\n")
        f.write("---\n\n")
        f.write(markdown)
        f.write(f"\n\n原文链接：{url}\n")

    print(f"✅ 文章已保存: {md_path}")

if __name__ == "__main__":
    url = input("请输入文章链接: ").strip()
    if not url:
        print("❌ 链接不能为空")
        sys.exit(1)

    category = input("请输入分类（默认 web3）: ").strip()
    if not category:
        category = "web3"

    download_article(url, category)