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

def setup_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def get_detail_info(driver, url):
    """詳細ページから会場と時間を抽出する（タイトルは一覧から引き継ぐため、ここでは補完のみ）"""
    venue = "詳細を確認"
    time_info = ""
    try:
        driver.get(url)
        # 記事内容または特定のクラスが出るまで待機
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".article__content, .body, .p-clubScheduleArticle, .tribe-events-single-event-description, .c-clubWysiwyg")))
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # --- DSPM系 (さよステ/meme) / Tribe系 ---
        v_el = soup.select_one('.p-clubScheduleArticle__place__text span, .p-clubScheduleDetail__venue, .tribe-events-pro-venue__name')
        t_el = soup.select_one('.p-clubScheduleArticle__description__item, .p-clubScheduleDetail__time, .tribe-events-pro-full-date')
        if v_el: venue = v_el.get_text(strip=True)
        if t_el: time_info = t_el.get_text(strip=True)
        
        # dateTimeからの時間抽出（さよステ等）
        if not time_info:
            dt_el = soup.select_one('.p-clubScheduleArticle__dateTime span')
            if dt_el: time_info = re.sub(r'^\d{4}/\d{2}/\d{2}\(.\)\s*', '', dt_el.get_text(strip=True))

        # --- 虹コン / 本文直接書きパターン ---
        content = soup.select_one('.article__content, .body, .c-clubWysiwyg')
        if content:
            # 見出しタグをチェック
            h4_tags = soup.select('h4')
            for h4 in h4_tags:
                h4_text = h4.get_text()
                p_next = h4.find_next_sibling('p')
                if not p_next: continue
                if "日時/場所" in h4_text:
                    lines = [ln.strip() for ln in p_next.get_text("\n").split("\n") if ln.strip()]
                    if len(lines) >= 1: time_info = re.sub(r'^\d+/\d+\(.\)\s*', '', lines[0])
                    if len(lines) >= 2: venue = lines[1]
                elif "日時" in h4_text:
                    time_info = re.sub(r'^\d{4}年\d{1,2}月\d{1,2}日\(.\)\s*', '', p_next.get_text(strip=True))
                elif "会場" in h4_text:
                    venue = p_next.get_text(strip=True)

            # meme等の「■」書き込みパターン
            if venue == "詳細を確認" or not time_info:
                for line in content.get_text("\n").split("\n"):
                    if "■場所" in line or "■会場" in line:
                        venue = line.split("：")[-1].split(":")[-1].strip()
                    if "■時間" in line:
                        time_info = line.split("：")[-1].split(":")[-1].strip()

    except Exception as e:
        print(f"Detail parse error at {url}: {e}")
    
    return venue, time_info

def scrape_tribe(driver, name, url):
    events = []
    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".tribe-events-calendar-month__day")))
        time.sleep(5)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        for day in soup.select('.tribe-events-calendar-month__day'):
            dt = day.select_one('time').get('datetime') if day.select_one('time') else None
            if not dt: continue
            for a in day.select('a'):
                if a.get('href') and ("event-title-link" in str(a.get('class')) or "event-link" in str(a.get('class'))):
                    title = a.get_text(strip=True)
                    v, tm = get_detail_info(driver, a.get('href'))
                    events.append({"title": f"[{name}] {title}", "start": dt, "url": a.get('href'), "venue": v, "time": tm, "allDay": True})
                    driver.back() # 一覧に戻る
                    time.sleep(2)
    except: pass
    return events

def scrape_2zicon(driver):
    name = "虹コン"
    base = "https://2zicon.tokyo"
    events = []
    now = datetime.now()
    for i in range(0, 13):
        target = now + timedelta(days=31 * i)
        driver.get(f"{base}/information/schedule?getYear={target.year}&getMonth={target.month}")
        time.sleep(3)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        for it in soup.select('.info__item'):
            link = it.select_one('a.info__link')
            text_el = it.select_one('.info__text')
            if not link or not text_el: continue
            
            title = text_el.get_text(strip=True) # 一覧からタイトルを取得
            f_url = link.get('href') if link.get('href').startswith('http') else base + link.get('href')
            d_txt = it.select_one('.info__date').get_text()
            d_match = re.search(r'\d{4}.\d{2}.\d{2}', d_txt.replace('.', '-'))
            if d_match:
                v, tm = get_detail_info(driver, f_url)
                events.append({"title": f"[{name}] {title}", "start": d_match.group().replace('.', '-'), "url": f_url, "venue": v, "time": tm, "allDay": True})
    return events

def scrape_dspm(driver, name, base_url, menu_path):
    events = []
    now = datetime.now()
    for i in range(0, 13):
        target = now + timedelta(days=31 * i)
        t_m = f"{target.year}-{str(target.month).zfill(2)}"
        u = f"{base_url}{menu_path}?start={t_m}-01" if "schedules" in menu_path else f"{base_url}{menu_path}/{target.year}/{target.month}"
        driver.get(u)
        time.sleep(5)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        items = []
        if "vertical_calendar" in menu_path: # meme
            for li in soup.select('li.list-group-item'):
                t_tag, inner = li.select_one('time'), li.select_one('.fc-event-inner')
                if not t_tag or not inner: continue
                title = inner.get_text(strip=True)
                dm = re.findall(r'\d+', t_tag.get_text())
                if len(dm)<3: continue
                ds = f"{dm[0]}-{dm[1].zfill(2)}-{dm[2].zfill(2)}"
                for a in li.select('a.tag-event, a.tag-live'):
                    items.append({"url": base_url + a.get('href'), "date": ds, "title": title})
        else: # sayostay
            for td in soup.select('td.fc-daygrid-day'):
                ds = td.get('data-date')
                if not ds or not ds.startswith(t_m): continue
                for a in td.select('a.fc-daygrid-event'):
                    t_el = a.select_one('.fc-event-title')
                    items.append({"url": base_url + a.get('href'), "date": ds, "title": t_el.get_text(strip=True) if t_el else ""})

        for it in items:
            v, tm = get_detail_info(driver, it['url'])
            events.append({"title": f"[{name}] {it['title']}", "start": it['date'], "url": it['url'], "venue": v, "time": tm, "allDay": True})
    return events

def main():
    driver = setup_driver()
    all_data = []
    all_data.extend(scrape_tribe(driver, "ChumToto", "https://chumtoto.jp/schedule/"))
    all_data.extend(scrape_tribe(driver, "きゅるして", "https://www.kyurushite.com/schedule/"))
    all_data.extend(scrape_2zicon(driver))
    all_data.extend(scrape_dspm(driver, "さよステ", "https://sayostay.dspm.jp", "/schedules/menu/18610"))
    all_data.extend(scrape_dspm(driver, "meme", "https://www.memetokyo.com", "/vertical_calendar"))
    driver.quit()
    unique_events = list({(ev['title'], ev['start']): ev for ev in all_data}.values())
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(unique_events, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
