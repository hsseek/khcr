import traceback

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
import sqlite

MAX_SCANNING_URL_SPAN = 5
MIN_SCANNING_URL_SPAN = 3
SCANNING_TIME_SPAN = 2.5  # seconds
MIN_PAUSE = 1.4
MAX_PAUSE = 3.2
SIZE_TOLERANCE = 128  # bytes


def log(message: str):
    with open(Path.LOG_PATH, 'a') as f:
        f.write(message + '\n')
    print(message)


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
        backup(file_path)
    else:  # HTTP status code 4XX/5XX
        log("Error: Download failed.(status code {}\n{})".format(r.status_code, r.text) + ' (%s)' % __get_str_time)


def backup(file_path: str):
    try:
        backup_path = Path.BACKUP_PATH
        copied_file_name = file_path.split('/')[-1].split('-')[-1]  # path/index-filename.png -> filename.png
        if copied_file_name.startswith('.'):  # glob won't detect hidden files with '/*'.
            copied_file_name = str(random.randint(0, 9)) + copied_file_name

        # Remove the previous file(s) and copy the new file.
        previous_files = glob.glob(Path.BACKUP_PATH + '*')
        for file in previous_files:
            os.remove(file)
        copyfile(file_path, backup_path + copied_file_name)
    except Exception as e:
        log('Error: Backup went wrong. Do not change the record.\t(%s)\n(%s)' % (__get_str_time(), e))


class Path:
    # urls and paths in String
    DRIVER_PATH = read_from_file('DRIVER_PATH.pv')
    ROOT_DOMAIN = read_from_file('ROOT_DOMAIN.pv')
    DOWNLOAD_PATH = read_from_file('DOWNLOAD_PATH.pv')
    BACKUP_PATH = read_from_file('BACKUP_PATH.pv')
    LOG_PATH = read_from_file('LOG_PATH.pv')


def __get_elapsed_time(start_time) -> float:
    end_time = datetime.datetime.now()
    return (end_time - start_time).total_seconds()


def extract_download_target(soup: BeautifulSoup) -> ():
    # If the image is still available.
    # Retrieve the image url
    target_tag = soup.find_all('link', {'rel': 'image_src'})
    if target_tag:
        if len(target_tag) > 1:
            log('Warning: Multiple image sources.\n' + str(target_tag))
        # Retrieve the file name
        dropdown_menus = soup.select('body div.container ul.dropdown-menu li a')
        url = target_tag[0]['href']  # url of the file to download
        try:
            # Split at ' : ' rather than remove 'FileName : ' not to be dependent on browser language.
            # Split at ' : ' rather than ':' to be more specific. The file name might contain ':'.
            name = dropdown_menus[0].contents[0].split(' : ')[-1].strip().replace(" ", "_")
            # The view count
            view_count_str = dropdown_menus[-3].contents[0].split(' : ')[-1].strip()
            view_count_digits = ""
            for char in view_count_str:
                if char.isdigit():
                    view_count_digits += char
            # The size
            size_str = dropdown_menus[1].contents[0].split(' : ')[-1].split(' ')[0]
            size = int(size_str.replace(',', ''))
            # The digitized index
            page_url = remove_extension(url)
            index = __format_url_index(__get_url_index(page_url))  # Convert to the integer index.
            storing_name = '%s-%02d-%s' % (index, int(view_count_digits), name)
        except Exception as e:
            # domain.com/image.jpg -> domain.com/image -> image
            storing_name = remove_extension(url).split('/')[-1]
            size = 0
            log('Error: Cannot retrieve the file data.\t(%s)\n%s' % (__get_str_time(), e))
        return url, storing_name, size


def upload_image() -> str:
    # A chrome web driver with headless option
    service = Service(Path.DRIVER_PATH)
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument('disable-gpu')
    # options.add_experimental_option("detach", True)  # TEST
    browser = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(browser, timeout=5)
    try:  # Open the browser and upload the last image.
        browser.get(Path.ROOT_DOMAIN)
        files_to_upload = glob.glob(Path.BACKUP_PATH + '*')  # Should be len() = 1
        if not files_to_upload:  # Empty
            log('Error: The last backup not available.\t(%s)' % __get_str_time())
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
        uploaded_url = remove_extension(image_url)  # domain.com/name
        log('%s uploaded on %s.\t(%s)' % (file_to_upload.split('/')[-1], uploaded_url, __get_str_time()))
        try:  # Delete the uploaded file.
            browser.find_element(By.XPATH, '/html/body/nav/div/div[2]/ul/li[4]/a').click()
            wait.until(expected_conditions.alert_is_present())
            browser.switch_to.alert.accept()
            wait.until(expected_conditions.presence_of_element_located((By.CLASS_NAME, 'page-wrapper')))
        except Exception as alert_exception:
            log('Error: Cannot delete the uploaded seed.(%s)\t(%s)' % (alert_exception, __get_str_time()))
        return uploaded_url
    except Exception as upload_exception:
        log('Error: Cannot upload seed.(%s)\t(%s)' % (upload_exception, __get_str_time()))
    finally:
        browser.quit()


# Split on the pattern, but always returning a list with length of 2.
def __split_on_last_pattern(string: str, pattern: str) -> ():
    last_piece = string.split(pattern)[-1]  # domain.com/image.jpg -> jpg
    leading_chunks = string.split(pattern)[:-1]  # [domain, com/image]
    leading_piece = pattern.join(leading_chunks)  # domain.com/image
    return leading_piece, last_piece  # (domain.com/image, jpg)


def remove_extension(string: str) -> str:
    return __split_on_last_pattern(string, '.')[0]


def __get_url_index(url: str) -> []:
    url_indices = []  # for example, url_indices = [3, 5, 1, 9] (a list of int)
    str_index = __split_on_last_pattern(url, '/')[-1]  # 'a3Fx' from 'https://domain.com/a3Fx'
    with open('SEQUENCE.pv', 'r') as file:
        sequence = file.read().split('\n')

    for char in str_index:  # a -> 3 -> F -> x
        for n, candidates in enumerate(sequence):
            if char == candidates:
                url_indices.append(n)  # Found the matching index
                break
    return url_indices


def __format_url_index(url_indices: ()) -> str:
    formatted_index = ''
    for index in url_indices:
        formatted_index += '%02d' % index
    return formatted_index


def get_next_url(url: str) -> str:
    url_index = __get_url_index(url)
    url_root = __split_on_last_pattern(url, '/')[0] + '/'  # 'https://domain.com/' from 'https://domain.com/a3Fx'

    with open('SEQUENCE.pv', 'r') as file:
        sequence = file.read().split('\n')

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
                    # Behavior not known. May happen in years.
    # url_index shift by 1, so that [3, 5, 2, 0]

    for index in url_index:
        url_root += sequence[index]
    return url_root


def __get_str_time() -> str:
    return str(datetime.datetime.now()).split('.')[0]


while True:
    ignored_database = sqlite.IgnoreListDatabase()
    try:
        # Upload a file to get the start of a scanning sequence
        occupied_url = upload_image()
        url_to_scan = get_next_url(occupied_url)

        # If fails 1000 times in a row, something must have went wrong.
        failure_count = 0
        MAX_FAILURE = 1000
        somethings_wrong = False
        detected_in_span = False
        first_trial_time = datetime.datetime.now()

        # Time span between successful downloads
        last_downloaded = datetime.datetime.now()

        while not somethings_wrong:  # Scan a couple of next urls
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
                        file_url = target[0]
                        local_name = target[1]
                        if file_url.split('.')[-1] == 'dn':
                            # Print the span without updating last_downloaded
                            download_span = int(__get_elapsed_time(last_downloaded)) / 60
                            log('[ - ] in %.1f\t: %s-*.dn "삭제된 이미지입니다."\t(%s)' %
                                (download_span, __split_on_last_pattern(local_name, '-')[0], __get_str_time()))
                        else:  # A valid link
                            # Visualization
                            checks = '['
                            for j in range(i):
                                checks += ' -'
                            checks += ' V ]'
                            # The minutes spent between consecutive successful downloads
                            download_span = int(__get_elapsed_time(last_downloaded)) / 60
                            last_downloaded = datetime.datetime.now()  # Update for the later use.

                            # While the link is valid, check the file is in the ignored list.
                            ignored_list = ignored_database.fetch_ins()
                            # The information of the uploaded file
                            name_with_extension = local_name[12:]  # Dropping '19102312-02-'
                            uploaded_file_name = remove_extension(name_with_extension)
                            uploaded_size = target[2]
                            for k, ignored_file in enumerate(ignored_list):
                                ignored_size = ignored_list[k][2]  # 282719 from (12, aa, 282719)
                                ignored_pattern = ignored_list[k][1]  # 'aa'
                                db_id = ignored_list[k][0]  # '12'
                                if not ignored_size:
                                    log('Error: The file size has not been specified for %s.' % ignored_pattern)
                                    ignored_database.unregister(db_id)
                                else:  # Check the sizes match.
                                    if ignored_size - SIZE_TOLERANCE < uploaded_size < ignored_size + SIZE_TOLERANCE:
                                        # The size match.
                                        # Check the names match then: 'aa' from (3, aa, 282719) in file name?
                                        if ignored_pattern in uploaded_file_name:
                                            # A match found. While the link is valid, the file should be ignored.
                                            ignored_database.increase_count(db_id)
                                            log('%s in %.1f\t: (ignored) %s\t(%s)' %
                                                (checks, download_span, uploaded_file_name, __get_str_time()))
                                            break  # Stop matching the sizes.
                            else:  # A valid file: start downloading.
                                download(file_url, local_name)  # The url of the file and the file name for a reference.
                                # [ V ] in 2.3  : filename.jpg  (2021-01-23 12:34:56)
                                log('%s in %.1f\t: %s\t(%s)' % (checks, download_span, local_name, __get_str_time()))

                        break  # Scanning span must be shifted.
                    else:  # Move to the next target in the span.
                        url_to_scan = get_next_url(url_to_scan)

                elapsed_time = __get_elapsed_time(scan_start_time)
                time_left = SCANNING_TIME_SPAN - elapsed_time
                report = ''
                # Implement jitter.
                if time_left > 0:
                    pause = random.uniform(MIN_PAUSE, MAX_PAUSE)
                    time.sleep(pause)
                    report += 'Scanned for %.1f(%.1f)' % ((pause + elapsed_time), elapsed_time)
                else:
                    log('\t\t\t\t: Scanned for %.1f"\t(%s)' % (elapsed_time, __get_str_time()))  # Scanning got slower.

                if detected_in_span:
                    failure_count = 0
                    detected_in_span = False  # Turn off the switch for the later use.
                else:
                    failure_count += 1
                    report += '\tNothing found over the span of %d.' % scanning_url_span
                    report += '\tConsecutive failures: %i \t(%s)' % (failure_count, __get_str_time())
                    print(report)

            else:  # Failure count reached the limit. Something went wrong.
                somethings_wrong = True
                loop_span = int(__get_elapsed_time(first_trial_time) / 60)
                log('Warning: Failed %d times in a row for %d minutes.\t(%s)' % (
                    MAX_FAILURE, loop_span, __get_str_time()))
    except Exception as main_loop_exception:
        log('Error: %s\t%s\n[Traceback]\n%s' % (main_loop_exception, __get_str_time(), traceback.format_exc()))
    finally:
        ignored_database.close_connection()
