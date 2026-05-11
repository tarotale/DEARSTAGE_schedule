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
    base_url = "https://chumtoto.jp/schedule/"
    driver = setup_driver()
    all_events = []

    try:
        print("ChumTotoのスケジュールを取得中（個別URL抽出あり）...")
        driver.get(base_url)
        time.sleep(8)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        days = soup.select('.tribe-events-calendar-month__day')
        
        for day in days:
            # 日付の取得
            time_tag = day.select_one('time.tribe-events-calendar-month__day-date-daynum')
            if not time_tag or not time_tag.has_attr('datetime'):
                continue
            date_str = time_tag['datetime']
            
            # イベント要素の抽出
            # aタグを基準に探し、その中のタイトルとhrefを取得する
            event_links = day.select('a.tribe-events-calendar-month__multiday-event-hidden-link, a.tribe-events-calendar-month__calendar-event-title-link')
            
            for link in event_links:
                href = link.get('href')
                title_el = link.select_one('h3') or link # h3があればそれを、なければlink自身のテキスト
                title = title_el.get_text(strip=True)
                
                if title and href:
                    all_events.append({
                        "title": f"[ChumToto] {title}",
                        "start": date_str,
                        "url": href, # ここを個別ページのURLに修正
                        "allDay": True
                    })
                    
    except Exception as e:
        print(f"ChumTotoでエラー発生: {e}")
    finally:
        driver.quit()

    return all_events

if __name__ == "__main__":
    results = scrape_chumtoto()
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"完了！ {len(results)} 件のイベント（個別リンク付き）を保存しました。")
