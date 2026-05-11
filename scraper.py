import os
import json
import time
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

def setup_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def parse_date(text):
    """テキストから正確な日付を抽出する。見つからない場合はNoneを返す"""
    # 2026.05.15 / 2026-05-15 / 2026/05/15
    match_full = re.search(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})', text)
    if match_full:
        return f"{match_full.group(1)}-{match_full.group(2).zfill(2)}-{match_full.group(3).zfill(2)}"
    
    # 05/15 / 05.15
    match_short = re.search(r'(\d{1,2})[./](\d{1,2})', text)
    if match_short:
        # 月が13以上（2026.26.05のような誤検知）を防ぐ
        m, d = int(match_short.group(1)), int(match_short.group(2))
        if 1 <= m <= 12 and 1 <= d <= 31:
            return f"2026-{str(m).zfill(2)}-{str(d).zfill(2)}"
    
    return None

def is_valid_event(title):
    """メニュー項目やゴミデータを除外する"""
    exclude_keywords = [
        "PROFILE", "CONTACT", "DISCOGRAPHY", "VIDEO", "INFORMATION", "SCHEDULE",
        "FANCLUB", "GOODS", "REGULATION", "MAIL MAGAZINE", "TICKET", "MOVIE",
        "GALLERY", "0イベント", "日付を選択", "カレンダー表示", "ビューのナビゲーション"
    ]
    # 除外ワードが完全に一致、またはタイトルが短すぎる場合は無効
    if any(k == title.strip() for k in exclude_keywords) or len(title) < 5:
        return False
    return True

def scrape_all():
    groups = {
        "ChumToto": "https://chumtoto.jp/schedule/",
        "虹コン": "https://2zicon.tokyo/information/schedule/",
        "さよステ": "https://sayostay.dspm.jp/schedules/menu/18610",
        "きゅるして": "https://www.kyurushite.com/schedule/",
        "meme tokyo.": "https://www.memetokyo.com/vertical_calendar"
    }
    
    driver = setup_driver()
    all_events = []

    for name, url in groups.items():
        try:
            print(f"Scraping {name}...")
            driver.get(url)
            time.sleep(8) # 読み込み待ち
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # ページ内のすべての「まとまり」を一旦取得
            elements = soup.find_all(['li', 'article', 'div', 'tr'])
            
            for el in elements:
                text = el.get_text(separator=' ', strip=True)
                
                # 1. 日付を抽出
                date_str = parse_date(text)
                if not date_str: continue
                
                # 2. タイトルをクリーンアップ（日付部分を削る）
                # 最初の20文字くらいにある日付や時刻のパターンを消す
                clean_title = re.sub(r'^\d+イベント, \d+|^\d{4}[./-]\d+[./-]\d+|^\d+[./]\d+', '', text).strip()
                
                if is_valid_event(clean_title):
                    all_events.append({
                        "title": f"[{name}] {clean_title[:50]}",
                        "start": date_str,
                        "url": url,
                        "allDay": True
                    })
        except Exception as e:
            print(f"Error {name}: {e}")

    driver.quit()
    
    # 完全に同じ予定を削除
    unique_events = []
    seen = set()
    for ev in all_events:
        identifier = (ev['title'], ev['start'])
        if identifier not in seen:
            unique_events.append(ev)
            seen.add(identifier)

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(unique_events, f, ensure_ascii=False, indent=2)
    print(f"Success! Saved {len(unique_events)} events.")

if __name__ == "__main__":
    scrape_all()
