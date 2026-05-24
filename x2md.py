import os
import sys
import re
import json
import argparse
import requests
from datetime import datetime
import time
from playwright.sync_api import sync_playwright
from markdownify import markdownify as md
from bs4 import BeautifulSoup

STORAGE_STATE = "storage_state.json"
BASE_PATH = "./source/_posts"
JINA_READER = "https://r.jina.ai/"


def clean_html(html):
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        alt = img.get("alt")
        src = img.get("src", "")
        if "emoji" in src or "twemoji" in src:
            img.replace_with(alt if alt else "🖼️")
    return str(soup)


def extract_title(text: str) -> str:
    if not text:
        return "untitled"
    first_line = text.strip().split("\n")[0]
    return first_line[:50].strip() or "untitled"


def parse_tweet_id(tweet_url: str):
    match = re.findall(r'/status/(\d+)', tweet_url)
    return match[0] if match else None


def yaml_quote(value: str) -> str:
    return json.dumps(value or "", ensure_ascii=False)


def normalize_x_url(url: str) -> str:
    return url.replace("twitter.com/", "x.com/")


def extract_jina_title(title_line: str, body: str) -> str:
    title_line = title_line.strip()
    quoted = re.search(r'on X:\s*"(.+?)"\s*/ X$', title_line)
    if quoted:
        return quoted.group(1).strip()

    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("[!["):
            continue
        return line[:80].strip()
    return title_line.replace(" / X", "").strip() or "untitled"


def parse_jina_response(raw: str):
    if not raw or "Markdown Content:" not in raw:
        return None

    title_match = re.search(r"^Title:\s*(.+)$", raw, re.MULTILINE)
    body = raw.split("Markdown Content:", 1)[1].strip()
    if "Continue with Google" in body and "Email or username" in body:
        return None

    body = re.sub(r"^## Article\s*\n+", "", body).strip()
    body = re.sub(r"^## Conversation\s*\n+", "", body).strip()
    title = extract_jina_title(title_match.group(1) if title_match else "", body)
    return title, body


def fetch_with_jina(tweet_url: str):
    reader_url = f"{JINA_READER}{normalize_x_url(tweet_url)}"
    response = requests.get(reader_url, timeout=60)
    response.raise_for_status()
    return parse_jina_response(response.text)


def download_image_to_local(img_url: str, idx: int, tweet_id: str, output_dir="web3", folder_path=""):
    os.makedirs(folder_path, exist_ok=True)
    img_url = re.sub(r'name=\w+', 'name=large', img_url)
    local_filename = f"{idx}.jpg"
    local_path = os.path.join(folder_path, local_filename)
    try:
        r = requests.get(img_url, timeout=15)
        if r.status_code == 200:
            with open(local_path, "wb") as f:
                f.write(r.content)
            rel_path = f"{output_dir}/{tweet_id}/{local_filename}"
            return rel_path
    except Exception:
        pass
    return None


def build_result(**kwargs):
    result = {
        "ok": False,
        "tweet_id": None,
        "title": None,
        "category": None,
        "markdown_path": None,
        "post_dir": None,
        "source_url": None,
        "already_exists": False,
        "message": None,
        "error": None,
    }
    result.update(kwargs)
    return result


def download_tweet(tweet_url, category="web3", overwrite=False, skip_if_exists=False, authorized_repost=False):
    tweet_id = parse_tweet_id(tweet_url)
    if not tweet_id:
        return build_result(error="invalid_tweet_url", message="无法解析推文 ID", source_url=tweet_url)

    base_path = BASE_PATH
    folder_path = os.path.join(base_path, tweet_id)
    md_path = os.path.join(base_path, f"{tweet_id}.md")

    if os.path.exists(md_path) and not overwrite:
        result = build_result(
            ok=True,
            tweet_id=tweet_id,
            category=category,
            markdown_path=os.path.abspath(md_path),
            post_dir=os.path.abspath(folder_path),
            source_url=tweet_url,
            already_exists=True,
            message="markdown already exists",
        )
        if skip_if_exists:
            return result
        return result

    os.makedirs(folder_path, exist_ok=True)

    fetch_method = "playwright"
    try:
        jina_result = fetch_with_jina(tweet_url)
    except Exception:
        jina_result = None

    if jina_result:
        md_title, markdown = jina_result
        fetch_method = "jina"
        if not authorized_repost and len(markdown) > 4000:
            return build_result(
                error="authorization_required",
                message="Jina 已抓到长文 Markdown；如确认你拥有转载授权，请加 --authorized-repost 再写入全文。",
                tweet_id=tweet_id,
                source_url=tweet_url,
                category=category,
                markdown_path=os.path.abspath(md_path),
                post_dir=os.path.abspath(folder_path),
            )
    else:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = (
                    browser.new_context(storage_state=STORAGE_STATE)
                    if os.path.exists(STORAGE_STATE)
                    else browser.new_context()
                )
                page = context.new_page()
                page.goto(tweet_url, timeout=30000)
                for _ in range(2):
                    page.mouse.wheel(0, 3000)
                    time.sleep(1)

                article = page.locator("article").first
                md_title = extract_title(article.locator('[data-testid="tweetText"] span').first.inner_text())
                tweet_blocks = article.locator('[data-testid="tweetText"]').all()
                all_html = "\n\n".join([block.inner_html() for block in tweet_blocks])
                html_content = clean_html(all_html)
                markdown = md(html_content, heading_style="ATX", strip=["svg", "style"])

                image_urls = []
                for img in article.locator('img').evaluate_all("els => els.map(e => ({alt:e.alt, src:e.src}))"):
                    src = img.get('src', '')
                    alt = img.get('alt', '')
                    if 'pbs.twimg.com/media/' in src and alt == 'Image' and src not in image_urls:
                        image_urls.append(src)

                image_markdown = []
                for idx, img_url in enumerate(image_urls, start=1):
                    rel_path = download_image_to_local(img_url, idx, tweet_id, output_dir=category, folder_path=folder_path)
                    if rel_path:
                        image_markdown.append(f"![Image]({rel_path})")

                if image_markdown:
                    markdown = markdown.rstrip() + "\n\n" + "\n\n".join(image_markdown)
                browser.close()
        except Exception as e:
            return build_result(
                error="fetch_failed",
                message="抓取失败",
                tweet_id=tweet_id,
                source_url=tweet_url,
                category=category,
                markdown_path=os.path.abspath(md_path),
                post_dir=os.path.abspath(folder_path),
                ) | {"details": str(e)}

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(f"title: {yaml_quote(md_title)}\n")
        f.write(f"date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("categories:\n")
        f.write(f"  - {category}\n")
        f.write("tags:\n")
        f.write("  - 转载\n")
        f.write(f"source_url: {yaml_quote(tweet_url)}\n")
        f.write(f"tweet_id: \"{tweet_id}\"\n")
        f.write(f"sync_method: {fetch_method}\n")
        f.write("---\n\n")
        f.write(markdown)
        f.write(f"\n\n原文链接：{tweet_url}\n")

    return build_result(
        ok=True,
        tweet_id=tweet_id,
        title=md_title,
        category=category,
        markdown_path=os.path.abspath(md_path),
        post_dir=os.path.abspath(folder_path),
        source_url=tweet_url,
        already_exists=False,
        message=f"tweet saved via {fetch_method}",
    )


def main():
    parser = argparse.ArgumentParser(description="Download X post and convert to Hexo markdown")
    parser.add_argument("--url", help="X/Twitter status URL")
    parser.add_argument("--category", default="web3", help="Hexo category (default: web3)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite markdown if exists")
    parser.add_argument("--skip-if-exists", action="store_true", help="Return success without rewriting when target exists")
    parser.add_argument("--authorized-repost", action="store_true", help="Confirm you have permission to save long-form source text")
    parser.add_argument("--json", action="store_true", help="Print structured JSON result")
    args = parser.parse_args()

    tweet_url = args.url
    if not tweet_url and sys.stdin.isatty():
        tweet_url = input("请输入推文链接: ").strip()
    if not tweet_url:
        result = build_result(error="missing_url", message="链接不能为空")
        print(json.dumps(result, ensure_ascii=False) if args.json else "❌ 链接不能为空")
        sys.exit(1)

    result = download_tweet(
        tweet_url=tweet_url,
        category=args.category,
        overwrite=args.overwrite,
        skip_if_exists=args.skip_if_exists,
        authorized_repost=args.authorized_repost,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            if result.get("already_exists"):
                print(f"ℹ️ 已存在: {result['markdown_path']}")
            else:
                print(f"✅ 推文已保存: {result['markdown_path']}")
        else:
            print(f"❌ {result.get('message') or result.get('error')}")
            if result.get("details"):
                print(result["details"])

    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
