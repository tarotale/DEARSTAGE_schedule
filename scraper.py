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

def parse_date(date_text):
    """'2026.05.15' や '5/15' などの文字列から ISO形式 '2026-05-15' を抽出する"""
    today = datetime.now()
    # 数字を抽出
    nums = re.findall(r'\d+', date_text)
    if len(nums) >= 3: # YYYY MM DD
        return f"{nums[0]}-{nums[1].zfill(2)}-{nums[2].zfill(2)}"
    elif len(nums) == 2: # MM DD (年は今年と仮定)
        return f"{today.year}-{nums[0].zfill(2)}-{nums[1].zfill(2)}"
    return today.strftime('%Y-%m-%d')

def scrape_all():
    groups = {
        "ちゅむとて": {"url": "https://chumtoto.jp/schedule/", "selector": ".schedule_list_item, .event-item"},
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
            time.sleep(6) # JS読み込み待ちを少し長めに
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # 各グループの共通的なリスト要素を探す
            items = soup.select(info['selector'])
            
            # もしセレクタで見つからない場合は広めに探す
            if not items:
                items = soup.find_all(['li', 'article', 'div'], class_=re.compile(r'item|schedule|event', re.I))

            for item in items:
                text = item.get_text(separator=' ', strip=True)
                if not text or len(text) < 10: continue
                
                # 日付とタイトルを分離する簡易ロジック
                # 多くのサイトはテキストの冒頭に日付がある
                date_str = parse_date(text[:20]) 
                title = text.replace('\n', ' ').strip()[:100] # 改行を消して100文字まで
                
                all_events.append({
                    "title": f"[{name}] {title}",
                    "start": date_str,
                    "url": info['url'],
                    "allDay": True,
                    "className": f"group-{name}" # CSSで色分け用
                })
        except Exception as e:
            print(f"Error {name}: {e}")

    driver.quit()
    
    # 重複削除（タイトルと日付が同じものを消す）
    unique_events = list({(ev['title'], ev['start']): ev for ev in all_events}.values())

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(unique_events, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(unique_events)} events.")

if __name__ == "__main__":
    scrape_all()
