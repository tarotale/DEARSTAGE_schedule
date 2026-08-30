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
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# --- 共通セットアップ ---
def setup_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def get_detail_info(driver, url):
    """詳細ページから会場と時間を抽出する（きゅるしての時間取得バグ修正版）"""
    venue = "詳細を確認"
    time_info = ""
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # 1. 構造化タグ優先
        v_el = soup.select_one('.p-clubScheduleArticle__place__text span, .p-clubScheduleDetail__venue, .tribe-events-pro-venue__name, .tribe-venue')
        t_el = soup.select_one('.p-clubScheduleArticle__description__item, .p-clubScheduleDetail__time, .tribe-events-pro-full-date, .tribe-events-schedule')
        if v_el: venue = v_el.get_text(strip=True)
        if t_el: time_info = t_el.get_text(strip=True)
        
        # 2. 本文テキスト解析
        content = soup.select_one('.common__article, .article__content, .body, .c-clubWysiwyg, .tribe-events-single-event-description, .p-clubScheduleArticle__description')
        
        if content:
            # --- パターンA: 見出し(h4, strong)と内容が分かれている ---
            for tag in content.find_all(['h4', 'strong']):
                label = tag.get_text(strip=True)
                
                # 直後のテキスト、または次のタグを取得
                data = ""
                if tag.next_sibling and isinstance(tag.next_sibling, str):
                    data = tag.next_sibling.strip()
                
                if not data or data in ["：", ":"]:
                    next_el = tag.find_next(['p', 'span'])
                    if next_el: data = next_el.get_text(strip=True)

                # --- きゅるして対策: 「日程」は無視し、「時間」を優先的に取得 ---
                if "時間" in label or "公演時間" in label:
                    time_info = data.replace("：", "").replace(":", "").strip()
                elif ("日時" in label) and not time_info: # 時間がまだ取れていない場合のみ日時をチェック
                    time_info = data.replace("：", "").replace(":", "").strip()
                elif "場所" in label or "会場" in label:
                    venue = data.replace("：", "").replace(":", "").strip()

            # --- パターンB: 1つのタグ内に改行区切りで書かれている（ChumTotoやmemeなど） ---
            if venue == "詳細を確認" or not time_info or time_info == "":
                lines = [line.strip() for line in content.get_text("\n").split("\n") if line.strip()]
                for line in lines:
                    if any(k in line for k in ["■場所", "■会場", "会場：", "会場:", "場所：", "場所:"]):
                        res = re.sub(r'^(■場所|■会場|会場|場所)[：:]\s*', '', line).strip()
                        if res: venue = res
                    if any(k in line for k in ["■時間", "時間：", "時間:", "公演時間"]):
                        res = re.sub(r'^(■時間|公演時間|時間)[：:]\s*', '', line).strip()
                        if res: time_info = res

        # 3. 最終フォールバック
        if not time_info:
            dt_el = soup.select_one('.p-clubScheduleArticle__dateTime span, .article__date')
            if dt_el: 
                time_info = re.sub(r'^\d{4}[/.]\d{2}[/.]\d{2}\(.\)\s*', '', dt_el.get_text(strip=True))

    except Exception as e:
        print(f"Detail parse warning at {url}: {e}")
    
    return venue, time_info

def scrape_tribe(driver, name, url):
    """ChumToto / きゅるして：一覧からURLを抜いて詳細解析"""
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
                events.append({"title": f"[{name}] {item['title']}", "start": item['date'], "url": item['url'], "venue": v, "time": tm, "allDay": True})
            next_link = soup.select_one('a.tribe-events-c-top-bar__nav-link--next, a.tribe-common-c-btn-icon--caret-right')
            current_url = next_link.get('href') if next_link and next_link.has_attr('href') else None
        except: break
    return events

def scrape_2zicon(driver):
    """虹コン：当月全ページ + 先12ヶ月巡回"""
    name = "虹コン"
    base_url = "https://2zicon.tokyo"
    events = []
    now = datetime.now()
    current_url = f"{base_url}/information/schedule/"
    while current_url:
        try:
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
        except: break
    for i in range(1, 13):
        target = now + timedelta(days=31 * i)
        cal_url = f"{base_url}/information/schedule?getYear={target.year}&getMonth={target.month}"
        try:
            driver.get(cal_url)
            time.sleep(3)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            for it in soup.select('.info__item'):
                link, text_el, d_el = it.select_one('a.info__link'), it.select_one('.info__text'), it.select_one('.info__date')
                if not link or not text_el or not d_el: continue
                title = text_el.get_text(strip=True)
                f_url = base_url + link.get('href') if link.get('href').startswith('/') else link.get('href')
                d_match = re.search(r'\d{4}-\d{2}-\d{2}', d_el.get_text(strip=True).replace('.', '-'))
                if d_match:
                    v, tm = get_detail_info(driver, f_url)
                    events.append({"title": f"[{name}] {title}", "start": d_match.group(), "url": f_url, "venue": v, "time": tm, "allDay": True})
        except: continue
    return events

def scrape_dspm(driver, name, base_url, menu_path):
    """さよステ / meme：先12ヶ月巡回"""
    events = []
    now = datetime.now()
    for i in range(0, 13):
        target = now + timedelta(days=31 * i)
        t_m = f"{target.year}-{str(target.month).zfill(2)}"
        u = f"{base_url}{menu_path}?start={t_m}-01" if "schedules" in menu_path else f"{base_url}{menu_path}/{target.year}/{target.month}"
        try:
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
        except: continue
    return events

def main():
    driver = setup_driver()
    all_data = []
    
    # 各グループのスクレイピング（ここは変更なし）
    all_data.extend(scrape_tribe(driver, "ChumToto", "https://chumtoto.jp/schedule/"))
    all_data.extend(scrape_tribe(driver, "きゅるして", "https://www.kyurushite.com/schedule/"))
    all_data.extend(scrape_2zicon(driver))
    all_data.extend(scrape_dspm(driver, "さよステ", "https://sayostay.dspm.jp", "/schedules/menu/18610"))
    all_data.extend(scrape_dspm(driver, "meme", "https://www.memetokyo.com", "/vertical_calendar"))
    
    driver.quit()

    # 1. 重複排除
    unique_events = list({(ev['title'], ev['start']): ev for ev in all_data}.values())

    # 2. 【ここから追加】前回保存したデータを読み込んで比較する
    old_data_dict = {}
    if os.path.exists('data.json'):
        try:
            with open('data.json', 'r', encoding='utf-8') as f:
                old_list = json.load(f)
                # タイトルと日付をキーにして、既存の追加日時(added_at)を保持する
                old_data_dict = {(ev['title'], ev['start']): ev.get('added_at') for ev in old_list}
        except Exception as e:
            print(f"前回のデータ読み込みに失敗しました: {e}")

    # 3. 現在の時刻を取得
    current_now = datetime.now().isoformat()

    # 4. 各イベントに追加日時を付与
    for ev in unique_events:
        key = (ev['title'], ev['start'])
        if key in old_data_dict and old_data_dict[key]:
            # すでに知っているイベントなら、前回の追加日時を維持
            ev['added_at'] = old_data_dict[key]
        else:
            # 新しく見つけたイベントなら、今の時間をセット
            ev['added_at'] = current_now

    # 5. 保存
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(unique_events, f, ensure_ascii=False, indent=2)

    print(f"全工程完了。合計 {len(unique_events)} 件（内、新着チェック完了）")

if __name__ == "__main__":
    main()
