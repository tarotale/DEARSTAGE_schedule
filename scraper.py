import os
import json
import time
import re
from datetime import datetime, timedelta
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
    """ChumToto / きゅるして用：次月ボタンがある限り巡回"""
    events = []
    current_url = url
    while current_url:
        try:
            print(f"{name} 取得中: {current_url}")
            driver.get(current_url)
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
            next_link = soup.select_one('a.tribe-events-c-top-bar__nav-link--next, a.tribe-common-c-btn-icon--caret-right')
            current_url = next_link.get('href') if next_link and next_link.has_attr('href') else None
        except: break
    return events

def scrape_2zicon(driver):
    """虹コン用：当月 + 先1年分巡回"""
    name = "虹コン"
    base_url = "https://2zicon.tokyo"
    events = []
    # 当月全ページ
    current_url = f"{base_url}/information/schedule/"
    while current_url:
        try:
            print(f"{name} (通常) 取得中: {current_url}")
            driver.get(current_url)
            time.sleep(3)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            events.extend(extract_2zicon_items(soup, name))
            next_btn = soup.select_one('a.pagi__btn--next')
            current_url = (base_url + next_btn.get('href')) if next_btn and next_btn.has_attr('href') else None
        except: break
    # 先1年分
    now = datetime.now()
    for i in range(1, 13):
        target = now + timedelta(days=31 * i)
        cal_url = f"{base_url}/information/schedule?getYear={target.year}&getMonth={target.month}"
        try:
            print(f"{name} ({target.year}/{target.month}) 取得中...")
            driver.get(cal_url)
            time.sleep(3)
            events.extend(extract_2zicon_items(BeautifulSoup(driver.page_source, 'html.parser'), name))
        except: continue
    return events

def extract_2zicon_items(soup, name):
    """虹コンのページからイベント項目を抽出する共通関数"""
    items_found = []
    base_url = "https://2zicon.tokyo"
    
    items = soup.select('.info__item')
    for item in items:
        link_tag = item.select_one('a.info__link')
        date_tag = item.select_one('.info__date')
        text_tag = item.select_one('.info__text')
        if link_tag and date_tag and text_tag:
            href = link_tag.get('href')
            date_str = date_tag.get_text(strip=True).replace('.', '-')
            title = text_tag.get_text(strip=True)
            
            # URLの重複防止ロジック
            # すでに http から始まっている場合はそのまま、そうでなければドメインを付与
            if href.startswith('http'):
                full_url = href
            else:
                # 先頭が / で始まっていない場合も考慮
                full_url = base_url + (href if href.startswith('/') else '/' + href)
            
            date_match = re.search(r'\d{4}-\d{2}-\d{2}', date_str)
            if date_match:
                items_found.append({
                    "title": f"[{name}] {title}", 
                    "start": date_match.group(), 
                    "url": full_url, 
                    "allDay": True
                })
    return items_found

def scrape_sayostay(driver):
    """さよステ用：先1年分巡回"""
    name = "さよステ"
    base = "https://sayostay.dspm.jp"
    events = []
    now = datetime.now()
    for i in range(0, 13):
        target = now + timedelta(days=31 * i)
        cal_url = f"{base}/schedules/menu/18610?start={target.year}-{str(target.month).zfill(2)}-01"
        try:
            print(f"{name} ({target.year}/{target.month}) 取得中...")
            driver.get(cal_url)
            time.sleep(6)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            for day in soup.select('td.fc-daygrid-day'):
                d = day.get('data-date')
                if not d or not d.startswith(f"{target.year}-{str(target.month).zfill(2)}"): continue
                for item in day.select('a.fc-daygrid-event'):
                    title = item.select_one('.fc-event-title')
                    events.append({"title": f"[{name}] {title.get_text(strip=True) if title else ''}", "start": d, "url": base + item.get('href'), "allDay": True})
        except: continue
    return events

def scrape_memetokyo(driver):
    """meme tokyo. 用：先1年分巡回"""
    name = "meme"
    base = "https://www.memetokyo.com"
    events = []
    now = datetime.now()
    for i in range(0, 13):
        target = now + timedelta(days=31 * i)
        # URL形式を修正: /vertical_calendar/年/月
        cal_url = f"{base}/vertical_calendar/{target.year}/{target.month}"
        try:
            print(f"{name} ({target.year}/{target.month}) 取得中...")
            driver.get(cal_url)
            time.sleep(5)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            for item in soup.select('li.list-group-item'):
                time_tag = item.select_one('time')
                if not time_tag: continue
                dm = re.findall(r'\d+', time_tag.get_text(strip=True))
                if len(dm) < 3: continue
                ds = f"{dm[0]}-{dm[1].zfill(2)}-{dm[2].zfill(2)}"
                for ev in item.select('a.tag-event, a.tag-live'):
                    inner = ev.select_one('.fc-event-inner')
                    events.append({"title": f"[{name}] {inner.get_text(strip=True) if inner else ''}", "start": ds, "url": base + ev.get('href'), "allDay": True})
        except: continue
    return events

def main():
    driver = setup_driver()
    all_data = []
    all_data.extend(scrape_tribe_events(driver, "ChumToto", "https://chumtoto.jp/schedule/"))
    all_data.extend(scrape_tribe_events(driver, "きゅるして", "https://www.kyurushite.com/schedule/"))
    all_data.extend(scrape_2zicon(driver))
    all_data.extend(scrape_sayostay(driver))
    all_data.extend(scrape_memetokyo(driver))
    driver.quit()
    unique_events = list({(ev['title'], ev['start']): ev for ev in all_data}.values())
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(unique_events, f, ensure_ascii=False, indent=2)
    print(f"全工程完了。合計 {len(unique_events)} 件")

if __name__ == "__main__":
    main()
