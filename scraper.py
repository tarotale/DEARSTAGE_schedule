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
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def scrape_chumtoto():
    url = "https://chumtoto.jp/schedule/"
    driver = setup_driver()
    all_events = []

    try:
        print("ChumTotoのスケジュールを取得中...")
        driver.get(url)
        # JavaScriptの描画を待機（少し長めに設定）
        time.sleep(8)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # カレンダーの「日（1日分）」を表すグリッド要素をすべて取得
        days = soup.select('.tribe-events-calendar-month__day')
        
        for day in days:
            # 1. その日の日付(YYYY-MM-DD)を取得
            time_tag = day.select_one('time.tribe-events-calendar-month__day-date-daynum')
            if not time_tag or not time_tag.has_attr('datetime'):
                continue
            date_str = time_tag['datetime']
            
            # 2. その日の中にあるイベントをすべて取得
            # 送っていただいたタグに合わせてセレクタを指定
            event_titles = day.select('.tribe-events-calendar-month__multiday-event-hidden-title, .tribe-events-calendar-month__calendar-event-title')
            
            for ev in event_titles:
                title = ev.get_text(strip=True)
                if title:
                    all_events.append({
                        "title": f"[ChumToto] {title}",
                        "start": date_str,
                        "url": url,
                        "allDay": True
                    })
                    
    except Exception as e:
        print(f"ChumTotoでエラー発生: {e}")
    finally:
        driver.quit()

    return all_events

if __name__ == "__main__":
    # 今はChumTotoのみ実行して精度を確認
    results = scrape_chumtoto()
    
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"成功！ {len(results)} 件のイベントを data.json に保存しました。")
