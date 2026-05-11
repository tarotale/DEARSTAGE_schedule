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

def scrape_tribe_events(driver, name, url):
    """The Events Calendar系サイト共通の抽出ロジック"""
    events = []
    try:
        print(f"{name} のスケジュールを取得中...")
        driver.get(url)
        time.sleep(8)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        days = soup.select('.tribe-events-calendar-month__day')
        
        for day in days:
            time_tag = day.select_one('time.tribe-events-calendar-month__day-date-daynum')
            if not time_tag or not time_tag.has_attr('datetime'):
                continue
            date_str = time_tag['datetime']
            
            # aタグからタイトルと個別URLを取得
            event_links = day.select('a.tribe-events-calendar-month__multiday-event-hidden-link, a.tribe-events-calendar-month__calendar-event-title-link')
            
            for link in event_links:
                href = link.get('href')
                title_el = link.select_one('h3') or link
                title = title_el.get_text(strip=True)
                
                if title and href:
                    events.append({
                        "title": f"[{name}] {title}",
                        "start": date_str,
                        "url": href,
                        "allDay": True
                    })
    except Exception as e:
        print(f"{name} でエラー発生: {e}")
    return events

def main():
    driver = setup_driver()
    all_results = []

    # 同じシステムを使っているグループをリスト化
    tribe_sites = [
        {"name": "ChumToto", "url": "https://chumtoto.jp/schedule/"},
        {"name": "きゅるして", "url": "https://www.kyurushite.com/schedule/"}
    ]

    for site in tribe_sites:
        all_results.extend(scrape_tribe_events(driver, site['name'], site['url']))

    driver.quit()

    # JSON保存
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print(f"合計 {len(all_results)} 件のイベントを保存しました。")

if __name__ == "__main__":
    main()
