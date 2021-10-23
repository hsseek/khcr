from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from bs4 import BeautifulSoup
import random
import time
import os
import requests
import datetime

# Regarding scanning
last_downloaded_name = 'seller.jpg'
MAX_SCANNING_URL_SPAN = 12
MIN_SCANNING_URL_SPAN = 6
SCANNING_TIME_SPAN = 1.5  # seconds


def read_from_file(path: str):
    with open(path) as f:
        return f.read().strip('\n')


def download(url: str, file_name: str):
    # Set the absolute path to store the downloaded file.
    download_path = Path.DOWNLOAD_PATH
    if not os.path.exists(download_path):
        os.makedirs(download_path)  # create folder if it does not exist

    # Set the download target.
    r = requests.get(url, stream=True)
    file_path = os.path.join(download_path, file_name)
    if r.ok:
        with open(file_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 8):
                if chunk:
                    f.write(chunk)
                    f.flush()
                    os.fsync(f.fileno())
        print("Stored to", os.path.abspath(file_path))
    else:  # HTTP status code 4XX/5XX
        print("Download failed: status code {}\n{}".format(r.status_code, r.text))


class Path:
    # urls and paths in String
    DRIVER_PATH = read_from_file('DRIVER_PATH.pv')
    ROOT_DOMAIN = read_from_file('ROOT_DOMAIN.pv')
    DOWNLOAD_PATH = read_from_file('DOWNLOAD_PATH.pv')


def get_elapsed_time(start_time):
    end_time = datetime.datetime.now()
    return (end_time - start_time).total_seconds()


def upload_image() -> str:
    # A chrome web driver with headless option
    service = Service(Path.DRIVER_PATH)
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument('disable-gpu')
    # options.add_experimental_option("detach", True)  # TEST
    browser = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(browser, 5)  # Upload page loading timeout: 5s

    # Open the browser and upload the last image.
    browser.get(Path.ROOT_DOMAIN)
    browser.find_element(By.XPATH, '//*[@id="media_up_btn"]').send_keys(Path.DOWNLOAD_PATH + last_downloaded_name)
    wait.until(expected_conditions.presence_of_element_located((By.CLASS_NAME, 'img-responsive')))

    image_url = extract_download_target(BeautifulSoup(browser.page_source, 'html.parser'))[0]  # domain.com/image.jpg
    uploaded_url = split_on_last_pattern(image_url, '.')[0]  # domain.com/name
    return uploaded_url


def extract_download_target(soup: BeautifulSoup) -> []:
    # If the image is still available.
    # Retrieve the image url
    target_tag = soup.select_one('link')
    if not target_tag:  # Empty
        if '/?err=1";' not in soup.select_one('script').text:  # ?err=1 redirects to "이미지가 삭제된 주소입니다."
            print('Unknown error with:\n\n' + soup.prettify())
    else:
        if target_tag['href'].split('.')[-1] == 'dn':
            print('삭제된 이미지입니다.jpg')
        else:
            # Retrieve the file name
            dropdown_menus = soup.select('body div.container ul.dropdown-menu li a')
            # Retrieve something like:
            # [<a href="javascript:;">FileName : seller.jpg</a>,
            # <a href="javascript:;">ViewCount : 23</a>, ...]
            url = target_tag['href']
            name = dropdown_menus[0].contents[0].replace('FileName : ', '').strip().replace(" ", "_")
            return [url, name]


def split_on_last_pattern(string: str, pattern: str) -> []:
    last_piece = string.split(pattern)[-1]  # domain.com/image.jpg -> jpg
    leading_chunks = string.split(pattern)[:-1]  # [domain, com/image]
    leading_piece = pattern.join(leading_chunks)  # domain.com/name
    return [leading_piece, last_piece]


def get_next_url(url: str) -> str:
    url_index = []
    url_root = split_on_last_pattern(url, '/')[0] + '/'  # 'https://domain.com/' from 'https://domain.com/a3Fx'
    str_index = split_on_last_pattern(url, '/')[-1]  # 'a3Fx' from 'https://domain.com/a3Fx'

    with open('SEQUENCE.pv', 'r') as file:
        sequence = file.read().split('\n')

    for char in str_index:
        for n, candidates in enumerate(sequence):
            if char == candidates:
                url_index.append(n)
                break
    # for example, url_index = [3, 5, 1, 9] (a list of int)

    if url_index[-1] != len(sequence) - 1:  # The last index is not '9'.
        url_index[-1] += 1
    else:  # ???9
        url_index[-1] = 0  # ???0
        if url_index[-2] != len(sequence) - 1:
            url_index[-2] += 1
        else:  # ??90
            url_index[-2] = 0  # ??00
            if url_index[-3] != len(sequence) - 1:
                url_index[-3] += 1
            else:  # ?900
                url_index[-3] = 0  # ?000
                if url_index[-4] != len(sequence) - 1:
                    url_index[-4] += 1
                else:
                    url_index[-4] = 0  # 0000
                    # TODO: Behavior not known. Notify.
    # url_index shift by 1, so that [3, 5, 2, 0]

    for index in url_index:
        url_root += sequence[index]
    return url_root


while True:
    # Upload a file to get the start of a scanning sequence
    occupied_url = upload_image()  # Intended
    print('A new file uploaded on ' + occupied_url)
    url_to_scan = get_next_url(occupied_url)

    # If fails 1000 times in a row, something must have went wrong.
    failure_count = 0
    MAX_FAILURE = 1000
    something_wrong = False
    detected_in_span = False

    while not something_wrong:
        if failure_count < MAX_FAILURE:
            # Set the timer.
            scan_start_time = datetime.datetime.now()

            url_to_scan = get_next_url(occupied_url)
            scanning_url_span = random.randint(MIN_SCANNING_URL_SPAN, MAX_SCANNING_URL_SPAN)
            for i in range(scanning_url_span):
                # Retrieve the next url
                source = requests.get(url_to_scan).text
                target = extract_download_target(BeautifulSoup(source, 'html.parser'))
                if target is not None:  # A file has been uploaded on the page.
                    occupied_url = url_to_scan  # Mark the url as occupied.
                    detected_in_span = True
                    # TODO: Download using another thread(For larger files)
                    target_url = target[0]
                    target_name = target[1]
                    download(target_url, target_name)
                    last_downloaded_name = target_name

                    # Report
                    checks = '['
                    for j in range(i):
                        checks += ' -'
                    checks += ' V ]'
                    print(checks)

                    break  # Scanning span must be shifted.
                else:  # Move to the next target.
                    url_to_scan = get_next_url(url_to_scan)

            elapsed_time = get_elapsed_time(scan_start_time)
            time_left = SCANNING_TIME_SPAN - elapsed_time
            # Implement jitter.
            if time_left > 0:
                pause = time_left * random.uniform(1, 2)
                time.sleep(pause)
                print('Scanning for %.1f(%.1f)' % ((pause + elapsed_time), elapsed_time))
            else:
                print('Scanning for (%.1f)' % elapsed_time)  # Hardly executed.

            if detected_in_span:
                failure_count = 0
                detected_in_span = False  # Turn off the switch for the later use.
            else:
                failure_count += 1
                print('Nothing found in the span.')
            print('Consecutive failures: %i\n' % failure_count)

        else:  # Failure count reached the limit. Something went wrong.
            something_wrong = True
