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
    """テキストから日付(YYYY-MM-DD)を抽出する"""
    today = datetime.now()
    # 2026.05.15 や 2026/05/15 などの形式を探す
    match_full = re.search(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})', text)
    if match_full:
        return f"{match_full.group(1)}-{match_full.group(2).zfill(2)}-{match_full.group(3).zfill(2)}"
    
    # 05/15 や 5.15 などの形式を探す
    match_short = re.search(r'(\d{1,2})[./](\d{1,2})', text)
    if match_short:
        return f"{today.year}-{match_short.group(1).zfill(2)}-{match_short.group(2).zfill(2)}"
    
    return today.strftime('%Y-%m-%d')

def scrape_all():
    # グループ名と設定を修正
    groups = {
        "ChumToto": {"url": "https://chumtoto.jp/schedule/", "selector": ".schedule_list_item, .event-list-item"},
        "虹コン": {"url": "https://2zicon.tokyo/information/schedule/", "selector": ".schedule_list_item, .contents-list__item"},
        "さよステ": {"url": "https://sayostay.dspm.jp/schedules/menu/18610", "selector": ".schedule-list-item, .contents-list__item"},
        "きゅるして": {"url": "https://www.kyurushite.com/schedule/", "selector": ".schedule_list_item, .event-list__item"},
        "meme tokyo.": {"url": "https://www.memetokyo.com/vertical_calendar", "selector": ".vertical-calendar__item, .schedule-item"}
    }
    
    driver = setup_driver()
    all_events = []

    for name, info in groups.items():
        try:
            print(f"Scraping {name}...")
            driver.get(info['url'])
            time.sleep(7) # 読み込み待ちを十分に確保
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            items = soup.select(info['selector'])
            
            # セレクタで見つからない場合の予備（広めに検索）
            if not items:
                items = soup.find_all(['li', 'article', 'div'], class_=re.compile(r'item|schedule|event', re.I))

            for item in items:
                raw_text = item.get_text(separator=' ', strip=True)
                if not raw_text or len(raw_text) < 5: continue
                
                date_str = parse_date(raw_text)
                # 日付以降のテキストをタイトルとして抽出
                clean_title = raw_text.replace('\n', ' ').strip()
                
                all_events.append({
                    "title": f"[{name}] {clean_title[:60]}",
                    "start": date_str,
                    "url": info['url'],
                    "allDay": True
                })
        except Exception as e:
            print(f"Error {name}: {e}")

    driver.quit()
    
    # 重複削除
    unique_events = list({(ev['title'], ev['start']): ev for ev in all_events}.values())

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(unique_events, f, ensure_ascii=False, indent=2)
    print(f"Finished. Saved {len(unique_events)} events.")

if __name__ == "__main__":
    scrape_all()
