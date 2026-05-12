import os
import json
import time
import re
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# --- 共通セットアップ ---
def setup_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def get_detail_info(driver, url):
    """詳細ページから会場と時間を抽出する（エラー耐性強化版）"""
    venue = "詳細を確認"
    time_info = ""
    try:
        driver.get(url)
        # bodyタグが表示されるまで待つ（確実性重視）
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # 1. 構造化タグ（さよステ・memeの一部・Tribe系）
        v_el = soup.select_one('.p-clubScheduleArticle__place__text span, .p-clubScheduleDetail__venue, .tribe-events-pro-venue__name, .tribe-venue')
        t_el = soup.select_one('.p-clubScheduleArticle__description__item, .p-clubScheduleDetail__time, .tribe-events-pro-full-date, .tribe-events-schedule')
        if v_el: venue = v_el.get_text(strip=True)
        if t_el: time_info = t_el.get_text(strip=True)
        
        # 2. 本文テキスト解析（虹コン・meme直接書き）
        content = soup.select_one('.article__content, .body, .c-clubWysiwyg, .tribe-events-single-event-description')
        if content:
            # 虹コン：見出しベース
            h4_tags = soup.select('h4')
            for h4 in h4_tags:
                text = h4.get_text()
                p_next = h4.find_next_sibling('p')
                if not p_next: continue
                if "日時/場所" in text:
                    lines = [ln.strip() for ln in p_next.get_text("\n").split("\n") if ln.strip()]
                    if len(lines) >= 1: time_info = re.sub(r'^\d+/\d+\(.\)\s*', '', lines[0])
                    if len(lines) >= 2: venue = lines[1]
                elif "日時" in text:
                    time_info = re.sub(r'^\d{4}年\d{1,2}月\d{1,2}日\(.\)\s*', '', p_next.get_text(strip=True))
                elif "会場" in text:
                    venue = p_next.get_text(strip=True)

            # meme：■記号ベース（30分バグ修正済み）
            if venue == "詳細を確認" or not time_info:
                for line in content.get_text("\n").split("\n"):
                    line = line.strip()
                    if "■場所" in line or "■会場" in line:
                        venue = re.sub(r'^■(場所|会場)[：:]\s*', '', line).strip()
                    if "■時間" in line:
                        time_info = re.sub(r'^■時間[：:]\s*', '', line).strip()

        # 最終手段：dateTime等から取得
        if not time_info:
            dt_el = soup.select_one('.p-clubScheduleArticle__dateTime span, .article__date')
            if dt_el: time_info = re.sub(r'^\d{4}[/.]\d{2}[/.]\d{2}\(.\)\s*', '', dt_el.get_text(strip=True))

    except Exception as e:
        print(f"Detail parse warning at {url}: {e}")
    
    return venue, time_info

# --- 各グループ巡回ロジック ---

def scrape_tribe(driver, name, url):
    """ChumToto / きゅるして：一覧から確実に取り、詳細情報を補完"""
    events = []
    current_url = url
    while current_url:
        try:
            print(f"{name} 取得中: {current_url}")
            driver.get(current_url)
            time.sleep(8)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            days = soup.select('.tribe-events-calendar-month__day')
            links_to_crawl = []

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
                        links_to_crawl.append({"title": title, "url": href, "date": date_str})

            for item in links_to_crawl:
                v, tm = get_detail_info(driver, item['url'])
                events.append({
                    "title": f"[{name}] {item['title']}", 
                    "start": item['date'], 
                    "url": item['url'], 
                    "venue": v, 
                    "time": tm, 
                    "allDay": True
                })

            next_link = soup.select_one('a.tribe-events-c-top-bar__nav-link--next, a.tribe-common-c-btn-icon--caret-right')
            current_url = next_link.get('href') if next_link and next_link.has_attr('href') else None
        except Exception as e:
            print(f"Error in {name}: {e}")
            break
    return events

def scrape_2zicon(driver):
    """虹コン用：当月(ページネーション含む) + 先1年分巡回"""
    name = "虹コン"
    base_url = "https://2zicon.tokyo"
    events = []
    now = datetime.now()

    # --- 1. 当月分の全ページ巡回 ---
    current_url = f"{base_url}/information/schedule/"
    while current_url:
        try:
            print(f"{name} (当月) 取得中: {current_url}")
            driver.get(current_url)
            time.sleep(3)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            for it in soup.select('.info__item'):
                link = it.select_one('a.info__link')
                text_el = it.select_one('.info__text')
                d_el = it.select_one('.info__date')
                if not link or not text_el or not d_el: continue
                
                title = text_el.get_text(strip=True)
                f_url = base_url + link.get('href') if link.get('href').startswith('/') else link.get('href')
                d_match = re.search(r'\d{4}-\d{2}-\d{2}', d_el.get_text(strip=True).replace('.', '-'))
                
                if d_match:
                    v, tm = get_detail_info(driver, f_url)
                    events.append({"title": f"[{name}] {title}", "start": d_match.group(), "url": f_url, "venue": v, "time": tm, "allDay": True})

            next_btn = soup.select_one('a.pagi__btn--next')
            current_url = (base_url + next_btn.get('href')) if next_btn and next_btn.has_attr('href') else None
        except Exception as e:
            print(f"{name} 当月エラー: {e}")
            break

    # --- 2. 先1年分の巡回 ---
    for i in range(1, 13):
        target = now + timedelta(days=31 * i)
        cal_url = f"{base_url}/information/schedule?getYear={target.year}&getMonth={target.month}"
        try:
            print(f"{name} ({target.year}/{target.month}) 取得中...")
            driver.get(cal_url)
            time.sleep(3)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            for it in soup.select('.info__item'):
                link = it.select_one('a.info__link')
                text_el = it.select_one('.info__text')
                d_el = it.select_one('.info__date')
                if not link or not text_el or not d_el: continue
                
                title = text_el.get_text(strip=True)
                f_url = base_url + link.get('href') if link.get('href').startswith('/') else link.get('href')
                d_match = re.search(r'\d{4}-\d{2}-\d{2}', d_el.get_text(strip=True).replace('.', '-'))
                
                if d_match:
                    v, tm = get_detail_info(driver, f_url)
                    events.append({"title": f"[{name}] {title}", "start": d_match.group(), "url": f_url, "venue": v, "time": tm, "allDay": True})
        except Exception as e:
            print(f"{name} {target.year}/{target.month} エラー: {e}")
            continue

    return events

def scrape_dspm(driver, name, base_url, menu_path):
    """さよステ / meme：先1年分巡回"""
    events = []
    now = datetime.now()
    for i in range(0, 13):
        target = now + timedelta(days=31 * i)
        t_m = f"{target.year}-{str(target.month).zfill(2)}"
        u = f"{base_url}{menu_path}?start={t_m}-01" if "schedules" in menu_path else f"{base_url}{menu_path}/{target.year}/{target.month}"
        try:
            print(f"{name} ({target.year}/{target.month}) 取得中...")
            driver.get(u)
            time.sleep(6)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            items = []
            
            if "vertical_calendar" in menu_path: # meme
                for li in soup.select('li.list-group-item'):
                    t_tag, inner = li.select_one('time'), li.select_one('.fc-event-inner')
                    if not t_tag or not inner: continue
                    title = inner.get_text(strip=True)
                    dm = re.findall(r'\d+', t_tag.get_text())
                    if len(dm) < 3: continue
                    ds = f"{dm[0]}-{dm[1].zfill(2)}-{dm[2].zfill(2)}"
                    for a in li.select('a.tag-event, a.tag-live'):
                        items.append({"url": base_url + a.get('href'), "date": ds, "title": title})
            else: # sayostay (前後の月の残像を弾く)
                for td in soup.select('td.fc-daygrid-day'):
                    ds = td.get('data-date')
                    if not ds or not ds.startswith(t_m): continue
                    for a in td.select('a.fc-daygrid-event'):
                        t_el = a.select_one('.fc-event-title')
                        items.append({"url": base_url + a.get('href'), "date": ds, "title": t_el.get_text(strip=True) if t_el else ""})
                        
            for it in items:
                v, tm = get_detail_info(driver, it['url'])
                events.append({"title": f"[{name}] {it['title']}", "start": it['date'], "url": it['url'], "venue": v, "time": tm, "allDay": True})
        except Exception as e:
            print(f"Error in {name} ({target.year}/{target.month}): {e}")
            continue
    return events

# --- メイン処理 ---
def main():
    driver = setup_driver()
    all_data = []
    
    # 1. ChumToto
    all_data.extend(scrape_tribe(driver, "ChumToto", "https://chumtoto.jp/schedule/"))
    # 2. きゅるして
    all_data.extend(scrape_tribe(driver, "きゅるして", "https://www.kyurushite.com/schedule/"))
    # 3. 虹コン
    all_data.extend(scrape_2zicon(driver))
    # 4. さよステ
    all_data.extend(scrape_dspm(driver, "さよステ", "https://sayostay.dspm.jp", "/schedules/menu/18610"))
    # 5. meme
    all_data.extend(scrape_dspm(driver, "meme", "https://www.memetokyo.com", "/vertical_calendar"))
    
    driver.quit()
    
    # 全データから重複（タイトルと日付
