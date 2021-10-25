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
from shutil import copyfile
import glob

# Regarding scanning
# TODO: Store it to another path (To prevent causing confusion with other files.)
MAX_SCANNING_URL_SPAN = 8
MIN_SCANNING_URL_SPAN = 4
SCANNING_TIME_SPAN = 1.5  # seconds


def read_from_file(path: str):
    with open(path) as f:
        return f.read().strip('\n')


def download(url: str, output_name: str):
    # Set the absolute path to store the downloaded file.
    download_path = Path.DOWNLOAD_PATH
    if not os.path.exists(download_path):
        os.makedirs(download_path)  # create folder if it does not exist

    # Set the download target.
    r = requests.get(url, stream=True)
    file_path = os.path.join(download_path, output_name)
    if r.ok:
        with open(file_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 8):
                if chunk:
                    f.write(chunk)
                    f.flush()
                    os.fsync(f.fileno())
        backup(file_path)
        print("Stored to", os.path.abspath(file_path))
    else:  # HTTP status code 4XX/5XX
        print("Download failed: status code {}\n{}".format(r.status_code, r.text))


def backup(file_path: str):
    try:
        backup_path = Path.BACKUP_PATH
        copied_file_name = file_path.split('/')[-1]
        copied_file_extension = copied_file_name.split('.')[-1]
        # Force the extension to jpg
        if copied_file_extension != 'jpg':
            copied_file_name = copied_file_name.split('.')[0] + '.jpg'
        print('%s to %s' % (file_path, backup_path + copied_file_name))

        # Remove the previous file(s) and copy the new file.
        previous_files = glob.glob(Path.BACKUP_PATH + '*')
        for file in previous_files:
            os.remove(file)
        copyfile(file_path, backup_path + copied_file_name)
    except Exception as e:
        print('Backup went wrong. Do not change the record.\nError: ' + str(e))


class Path:
    # urls and paths in String
    DRIVER_PATH = read_from_file('DRIVER_PATH.pv')
    ROOT_DOMAIN = read_from_file('ROOT_DOMAIN.pv')
    DOWNLOAD_PATH = read_from_file('DOWNLOAD_PATH.pv')
    BACKUP_PATH = read_from_file('BACKUP_PATH.pv')
    LOG_FILE_NAME = 'log'


def get_elapsed_time(start_time):
    end_time = datetime.datetime.now()
    return (end_time - start_time).total_seconds()


def extract_download_target(soup: BeautifulSoup) -> []:
    # If the image is still available.
    # Retrieve the image url
    target_tag = soup.select_one('link')
    if not target_tag:  # Empty
        if '/?err=1";' not in soup.select_one('script').text:
            # ?err=1 redirects to "이미지가 삭제된 주소입니다."
            # 업로드된 후 삭제된 경우에도, 아직 업로드되지 않은 경우에도 동일 메시지...
            print('Unknown error with:\n\n' + soup.prettify())
    else:
        if target_tag['href'].split('.')[-1] == 'dn':
            print('삭제된 이미지입니다.jpg')  # Likely to be a file in a wrong format
        else:
            # Retrieve the file name
            dropdown_menus = soup.select('body div.container ul.dropdown-menu li a')
            # Retrieve something like:
            # [<a href="javascript:;">FileName : seller.jpg</a>,
            # <a href="javascript:;">ViewCount : 23</a>, ...]
            # TODO: Retrieve and print ViewCount
            url = target_tag['href']  # url of the file to download
            try:
                # TODO: Format to 'source-count-filename'
                name = dropdown_menus[0].contents[0].replace('FileName : ', '').strip().replace(" ", "_")
            except Exception as e:
                # domain.com/image.jpg -> domain.com/image -> image
                name = split_on_last_pattern(url, '.')[0].split('/')[-1]
                print('Error: Cannot retrieve the file name.(%s)' + str(e))
            return [url, name]


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
    files_to_upload = glob.glob(Path.BACKUP_PATH + '*.jpg')  # Should be len() = 1
    if not files_to_upload:  # Empty
        print('Error: The last backup not available.')
        stored_files = glob.glob(Path.DOWNLOAD_PATH + '*.jpg')
        # Pick a random file among stored files.
        file_to_upload = glob.glob(Path.DOWNLOAD_PATH + '*.jpg')[random.randint(0, len(stored_files) - 1)]
        stored_file_name = file_to_upload.split('/')[-1]
        copyfile(file_to_upload, Path.BACKUP_PATH + stored_file_name)
    else:
        file_to_upload = files_to_upload[0]
    browser.find_element(By.XPATH, '//*[@id="media_up_btn"]').send_keys(file_to_upload)
    wait.until(expected_conditions.presence_of_element_located((By.CLASS_NAME, 'img-responsive')))

    image_url = extract_download_target(BeautifulSoup(browser.page_source, 'html.parser'))[0]  # domain.com/img.jpg
    uploaded_url = split_on_last_pattern(image_url, '.')[0]  # domain.com/name
    print(file_to_upload + ' uploaded on ' + uploaded_url)
    return uploaded_url


def split_on_last_pattern(string: str, pattern: str) -> []:
    last_piece = string.split(pattern)[-1]  # domain.com/image.jpg -> jpg
    leading_chunks = string.split(pattern)[:-1]  # [domain, com/image]
    leading_piece = pattern.join(leading_chunks)  # domain.com/image
    return [leading_piece, last_piece]  # [domain.com/image, jpg]


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
    url_to_scan = get_next_url(occupied_url)

    # If fails 1000 times in a row, something must have went wrong.
    failure_count = 0
    MAX_FAILURE = 2
    somethings_wrong = False
    detected_in_span = False

    while not somethings_wrong:
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
                    file_url = target[0]  # url of the file to download
                    file_name = target[1]
                    download(file_url, file_name)

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
                pause = random.uniform(1.5, 3)
                time.sleep(pause)
                print('Scanning for %.1f(%.1f)' % ((pause + elapsed_time), elapsed_time))
            else:
                print('Scanning for (%.1f)' % elapsed_time)  # Scanning got slower: Hardly executed.

            if detected_in_span:
                failure_count = 0
                detected_in_span = False  # Turn off the switch for the later use.
            else:
                failure_count += 1
                print('Nothing found over the span of %d.' % scanning_url_span)
            print('Consecutive failures: %i\n(%s)\n' % (failure_count, str(datetime.datetime.now()).split('.')[0]))

        else:  # Failure count reached the limit. Something went wrong.
            somethings_wrong = True
