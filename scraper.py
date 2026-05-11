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
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def scrape_tribe_events(driver, name, url):
    """ChumToto / きゅるして (The Events Calendar系)"""
    events = []
    try:
        print(f"{name} を取得中...")
        driver.get(url)
        time.sleep(8)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        days = soup.select('.tribe-events-calendar-month__day')
        for day in days:
            time_tag = day.select_one('time.tribe-events-calendar-month__day-date-daynum')
            if not time_tag or not time_tag.has_attr('datetime'): continue
            date_str = time_tag['datetime']
            event_links = day.select('a.tribe-events-calendar-month__multiday-event-hidden-link, a.tribe-events-calendar-month__calendar-event-title-link')
            for link in event_links:
                href = link.get('href')
                title_el = link.select_one('h3') or link
                title = title_el.get_text(strip=True)
                if title and href:
                    events.append({"title": f"[{name}] {title}", "start": date_str, "url": href, "allDay": True})
    except Exception as e: print(f"{name} エラー: {e}")
    return events

def scrape_2zicon(driver):
    """虹のコンキスタドール用"""
    name = "虹コン"
    url = "https://2zicon.tokyo/information/schedule/"
    events = []
    try:
        print(f"{name} を取得中...")
        driver.get(url)
        time.sleep(5)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        items = soup.select('.info__item')
        for item in items:
            link_tag = item.select_one('a.info__link')
            date_tag = item.select_one('.info__date')
            text_tag = item.select_one('.info__text')
            if link_tag and date_tag and text_tag:
                href = link_tag.get('href')
                date_str = date_tag.get_text(strip=True).replace('.', '-')
                title = text_tag.get_text(strip=True)
                date_match = re.search(r'\d{4}-\d{2}-\d{2}', date_str)
                if date_match:
                    events.append({"title": f"[{name}] {title}", "start": date_match.group(), "url": href, "allDay": True})
    except Exception as e: print(f"{name} エラー: {e}")
    return events

def scrape_sayostay(driver):
    """さよならステイチューン用"""
    name = "さよステ"
    base = "https://sayostay.dspm.jp"
    try:
        print(f"{name} を取得中...")
        driver.get(f"{base}/schedules/menu/18610")
        time.sleep(8)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        days = soup.select('td.fc-daygrid-day')
        events = []
        for day in days:
            d = day.get('data-date')
            if not d: continue
            for item in day.select('a.fc-daygrid-event'):
                h = item.get('href')
                full_url = base + h if h.startswith('/') else h
                title = item.select_one('.fc-event-title').get_text(strip=True)
                events.append({"title": f"[{name}] {title}", "start": d, "url": full_url, "allDay": True})
        return events
    except Exception as e: print(f"{name} エラー: {e}"); return []

def scrape_memetokyo(driver):
    """meme tokyo. 用"""
    name = "meme"
    base = "https://www.memetokyo.com"
    try:
        print(f"{name} を取得中...")
        driver.get(f"{base}/vertical_calendar")
        time.sleep(8)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        events = []
        items = soup.select('li.list-group-item')
        for item in items:
            # 日付抽出 2026年 05月 02日 -> 2026-05-02
            time_tag = item.select_one('time')
            if not time_tag: continue
            raw_date = time_tag.get_text(strip=True)
            date_match = re.findall(r'\d+', raw_date)
            if len(date_match) < 3: continue
            date_str = f"{date_match[0]}-{date_match[1].zfill(2)}-{date_match[2].zfill(2)}"
            
            # 同日内の全イベントを取得
            for ev in item.select('a.tag-event, a.tag-live'):
                h = ev.get('href')
                full_url = base + h if h.startswith('/') else h
                title = ev.select_one('.fc-event-inner').get_text(strip=True)
                events.append({"title": f"[{name}] {title}", "start": date_str, "url": full_url, "allDay": True})
        return events
    except Exception as e: print(f"{name} エラー: {e}"); return []

def main():
    driver = setup_driver()
    all_data = []
    # 実行
    all_data.extend(scrape_tribe_events(driver, "ChumToto", "https://chumtoto.jp/schedule/"))
    all_data.extend(scrape_tribe_events(driver, "きゅるして", "https://www.kyurushite.com/schedule/"))
    all_data.extend(scrape_2zicon(driver))
    all_data.extend(scrape_sayostay(driver))
    all_data.extend(scrape_memetokyo(driver))
    driver.quit()
    
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    print(f"全工程完了。合計 {len(all_data)} 件")

if __name__ == "__main__":
    main()
