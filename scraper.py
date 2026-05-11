import os
import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

def setup_driver():
    options = Options()
    options.add_argument('--headless=new')  # 画面なしで実行
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    # ブラウザであることを装う
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def scrape_all():
    urls = {
        "ちゅむとて": "https://chumtoto.jp/schedule/",
        "虹コン": "https://2zicon.tokyo/information/schedule/",
        "さよステ": "https://sayostay.dspm.jp/schedules/menu/18610", # JS必須
        "きゅるして": "https://www.kyurushite.com/schedule/",
        "meme tokyo.": "https://www.memetokyo.com/vertical_calendar"
    }
    
    driver = setup_driver()
    all_events = []

    for group, url in urls.items():
        try:
            driver.get(url)
            # JavaScriptの実行と読み込みを待つ（3〜5秒程度）
            time.sleep(5) 
            
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            # --- ここから各サイト別の抽出ロジック（例） ---
            # 実際のクラス名は、各サイトのHTML構造に合わせて詳細に書く必要があります。
            if group == "さよステ":
                # さよステ専用のタグ解析をここに記述
                items = soup.select(".schedule-list-item") # 仮のクラス名
                for item in items:
                    all_events.append({
                        "title": item.text.strip(),
                        "start": "2026-05-15", # 日付抽出ロジックが必要
                        "group": group,
                        "color": "#FF69B4" # さよステ用の色
                    })
            # ----------------------------------------
            
        except Exception as e:
            print(f"Error scraping {group}: {e}")

    driver.quit()
    
    # データを保存
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(all_events, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    scrape_all()
