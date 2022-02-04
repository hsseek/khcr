import traceback

from selenium import webdriver
# from selenium.webdriver.chrome.service import Service
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


def log(message: str, has_tst: bool = True):
    with open(Constants.LOG_PATH, 'a') as f:
        if has_tst:
            message += '\t(%s)' % __get_str_time()
        f.write(message + '\n')
    print(message)


def read_from_file(path: str):
    with open(path) as f:
        return f.read().strip('\n')


def build_tuple(path: str):
    content = read_from_file(path)
    return tuple(content.split('\n'))


def build_tuple_of_tuples(path: str):
    lines = build_tuple(path)
    info = []
    for line in lines:
        info.append(tuple(line.split(',')))
    return tuple(info)


def trim_logs(log_file_path: str):
    lines_threshold = 65536
    old_lines = 8192

    if not os.path.isfile(log_file_path):
        print('Warning: The file does not exist.')
        return

    with open(log_file_path, 'r') as fin:
        data = fin.read().splitlines(True)
        print('%d lines in %s.' % (len(data), log_file_path))
    if len(data) > lines_threshold:
        with open(log_file_path, 'w') as f_write:
            f_write.writelines(data[old_lines:])
            print('Trimmed first %d lines.' % old_lines)


def download(url: str, file_name: str) -> bool:
    try:
        # Set the absolute path to store the downloaded file.
        if not os.path.exists(Constants.DOWNLOAD_PATH):
            os.makedirs(Constants.DOWNLOAD_PATH)  # create folder if it does not exist

        # Set the download target.
        r = requests.get(url, stream=True)
        file_path = os.path.join(Constants.DOWNLOAD_PATH, file_name)
        if r.ok:
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 8):
                    if chunk:
                        f.write(chunk)
                        f.flush()
                        os.fsync(f.fileno())
            backup(file_path)
            return True
        else:  # HTTP status code 4XX/5XX
            log("Error: Download failed.(status code {}\n{})".format(r.status_code, r.text))
            return False
    except Exception as download_exception:
        log('Error: Download exception(%s).' % download_exception)
        return False


def backup(file_path: str):
    try:
        copied_file_name = file_path.split('/')[-1].split('-')[-1]  # path/index-filename.png -> filename.png
        if copied_file_name.startswith('.'):  # glob won't detect hidden files with '/*'.
            copied_file_name = str(random.randint(0, 9)) + copied_file_name

        # Remove the previous file(s) and copy the new file.
        previous_files = glob.glob(Constants.BACKUP_PATH + '*')
        for file in previous_files:
            os.remove(file)
        copyfile(file_path, Constants.BACKUP_PATH + copied_file_name)
    except Exception as e:
        log('Error: Backup went wrong(%s).' % e)


def __get_elapsed_sec(start_time) -> float:
    end_time = datetime.datetime.now()
    return (end_time - start_time).total_seconds()


def format_file_name(name: str):
    safe_char = '_'
    char_limit = 128
    nice_name = name
    if len(nice_name) > char_limit:
        nice_name = name[-char_limit:]
        print('Truncated a long file name: %s' % nice_name)
    for char in Constants.PROHIBITED_CHAR:
        nice_name = nice_name.strip(char)
        nice_name = nice_name.replace(char, safe_char)
    return nice_name


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
            name = dropdown_menus[0].string.split(' : ')[-1]
            formatted_name = format_file_name(remove_extension(name))
            category, extension = requests.session().get(url).headers['Content-Type'].split('/')
            if category != 'image':
                log('Error: %s is not an image.' % url)

            # The view count
            view_count_str = dropdown_menus[-3].string.split(' : ')[-1].strip()
            view_count_digits = ""
            for char in view_count_str:
                if char.isdigit():
                    view_count_digits += char
            # The size
            size_str = dropdown_menus[1].string.split(' : ')[-1].split(' ')[0]
            size = int(size_str.replace(',', ''))
            # The digitized index
            page_url = remove_extension(url)
            index = __format_url_index(__get_url_index(page_url))  # Convert to the integer index.

            storing_name = '%s-%02d-%s' % (index, int(view_count_digits), formatted_name + '.' + extension)
        except Exception as e:
            # domain.com/image.jpg -> domain.com/image -> image
            storing_name = remove_extension(url).split('/')[-1]
            size = 0
            log('Error: Cannot retrieve the file data.(%s)' % e)
        return url, storing_name, size


def upload_image() -> str:
    # A Chrome web driver with headless option
    # service = Service(Path.DRIVER_PATH)
    options = webdriver.ChromeOptions()
    options.add_argument('--proxy-server=socks5://127.0.0.1:9050')
    options.add_argument('headless')
    browser = webdriver.Chrome(executable_path=Constants.DRIVER_PATH, options=options)
    wait = WebDriverWait(browser, timeout=5)
    try:  # Open the browser and upload the last image.
        browser.get(Constants.ROOT_DOMAIN)
        files_to_upload = glob.glob(Constants.BACKUP_PATH + '*')  # Should be len() = 1
        if not files_to_upload:  # Empty
            log('Error: The last backup not available.')
            stored_files = glob.glob(Constants.DOWNLOAD_PATH + '*.jpg')
            # Pick a random file among stored files.
            file_to_upload = glob.glob(Constants.DOWNLOAD_PATH + '*.jpg')[random.randint(0, len(stored_files) - 1)]
            stored_file_name = file_to_upload.split('/')[-1]
            copyfile(file_to_upload, Constants.BACKUP_PATH + stored_file_name)
        else:
            file_to_upload = files_to_upload[0]
        browser.find_element(By.XPATH, '//*[@id="media_up_btn"]').send_keys(file_to_upload)
        wait.until(expected_conditions.presence_of_all_elements_located((By.CLASS_NAME, 'img-responsive')))

        # domain.com/img.jpg
        image_url = extract_download_target(BeautifulSoup(browser.page_source, Constants.HTML_PARSER))[0]
        uploaded_url = remove_extension(image_url)  # domain.com/name
        log('%s uploaded on %s.' % (file_to_upload.split('/')[-1], uploaded_url))
        try:  # Delete the uploaded file.
            browser.find_element(By.XPATH, '/html/body/nav/div/div[2]/ul/li[4]/a').click()
            wait.until(expected_conditions.alert_is_present())
            browser.switch_to.alert.accept()
            wait.until(expected_conditions.presence_of_all_elements_located((By.CLASS_NAME, 'page-wrapper')))
            print('Deleted the file on %s' % uploaded_url)
        except Exception as alert_exception:
            log('Error: Cannot delete the uploaded seed.(%s)' % alert_exception)
        return uploaded_url
    except Exception as upload_exception:
        log('Error: Cannot upload seed.(%s)' % upload_exception)
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


class Constants:
    HTML_PARSER = 'html.parser'
    MAX_SCANNING_URL_SPAN = 5
    MIN_SCANNING_URL_SPAN = 3
    SCANNING_TIME_SPAN = 2.5  # seconds
    MIN_PAUSE = 1.4
    MAX_PAUSE = 3.2
    RELOAD_LIMIT = 8
    IGNORED_FILENAME_PATTERNS, FILE_SIZE_THRESHOLD = build_tuple_of_tuples('IGNORE.pv')
    PROHIBITED_CHAR = (' ', '.', ',', ';', ':')
    ROOT_DOMAIN = read_from_file('ROOT_DOMAIN.pv')
    DRIVER_PATH, DOWNLOAD_PATH, BACKUP_PATH, LOG_PATH = build_tuple('LOCAL_PATHS.pv')


if __name__ == "__main__":
    while True:
        try:
            # Upload a file to get the start of a scanning sequence
            occupied_url = upload_image()
            url_to_scan = get_next_url(occupied_url)

            # If fails 1000 times in a row, something must have gone wrong.
            failure_count = 0
            MAX_FAILURE = 1000
            somethings_wrong = False
            detected_in_span = False
            first_trial_time = datetime.datetime.now()

            # Time span between successful downloads
            last_downloaded = datetime.datetime.now()

            while not somethings_wrong:  # Scan a couple of next urls
                if failure_count < MAX_FAILURE:
                    scan_start_time = datetime.datetime.now()  # Set the timer.
                    ignored_msg = ''  # For logging, in case.

                    url_to_scan = get_next_url(occupied_url)
                    scanning_url_span = random.randint(Constants.MIN_SCANNING_URL_SPAN, Constants.MAX_SCANNING_URL_SPAN)
                    if failure_count < 1:
                        scanning_url_span *= 3
                    for i in range(scanning_url_span):
                        # Retrieve the next url
                        source = requests.get(url_to_scan).text
                        target = extract_download_target(BeautifulSoup(source, Constants.HTML_PARSER))
                        if target is not None:  # A file has been uploaded on the page. BREAK at the end of it.
                            occupied_url = url_to_scan  # Mark the url as occupied.
                            detected_in_span = True  # To reset the failure count.
                            is_worth = True  # Determine if the file should be downloaded.

                            # Visualization
                            checks = '['
                            for j in range(i):
                                checks += ' -'
                            checks += ' V ]'

                            # The minutes spent between consecutive successful downloads
                            download_span = int(__get_elapsed_sec(last_downloaded)) / 60
                            last_downloaded = datetime.datetime.now()  # Update for the later use.

                            file_url, local_name, uploaded_size = target
                            uploaded_name = local_name[12:]  # Dropping '19102312-02-'

                            # The page occupied(so the span should be shifted), inspect the occupying file.
                            # 0. Prepare a well-defined file target.
                            for reload_count in range(Constants.RELOAD_LIMIT):
                                if uploaded_size > 0 and uploaded_name:
                                    break
                                else:
                                    # The image has not been properly loaded.
                                    log('Warning: The file cannot be specified. (%d/%d)'
                                        % (reload_count + 1, Constants.RELOAD_LIMIT))
                                    time.sleep(1)
                                    # Reload the page.
                                    source = requests.get(url_to_scan).text
                                    file_url, local_name, uploaded_size = \
                                        extract_download_target(BeautifulSoup(source, Constants.HTML_PARSER))
                            else:  # No name, no size even after reload limit.
                                log('Warning: Timeout reached.')
                                # Even though, cannot conclude it is not worth downloading. Don't turn down, unless...
                                if file_url.endswith('.dn'):
                                    # Assume that the file is in a wrong format.
                                    ignored_msg = 'A wrong format'
                                    is_worth = False

                            # Filter files.
                            # 1. Suspiciously small files
                            if is_worth:
                                if uploaded_size < int(Constants.FILE_SIZE_THRESHOLD[0]):
                                    ignored_msg = 'Too small(%s)' % uploaded_size
                                    is_worth = False

                            # 2. Files with suspicious names
                            if is_worth:
                                for ignored_filename_pattern in Constants.IGNORED_FILENAME_PATTERNS:
                                    if ignored_filename_pattern in remove_extension(uploaded_name):
                                        ignored_msg = '\'%s\' included' % ignored_filename_pattern
                                        is_worth = False
                                        break

                            # After all, still worth downloading: start downloading.
                            if is_worth:
                                dl_successful = download(file_url, local_name)
                                if dl_successful:
                                    # [ V ] in 2.3"  : filename.jpg
                                    log('%s in %.1f"\t: %s' % (checks, download_span, local_name))
                            else:
                                log('%s in %.1f"\t: (ignored: %s) %s' %
                                    (checks, download_span, ignored_msg, uploaded_name))
                            break  # Scanning span must be shifted.
                        else:  # Move to the next target in the span.
                            url_to_scan = get_next_url(url_to_scan)

                    elapsed_time = __get_elapsed_sec(scan_start_time)
                    time_left = Constants.SCANNING_TIME_SPAN - elapsed_time
                    report = ''
                    # Implement jitter.
                    if time_left > 0:
                        pause = random.uniform(Constants.MIN_PAUSE, Constants.MAX_PAUSE)
                        time.sleep(pause)
                        report += '%.1f(%.1f)\"' % ((pause + elapsed_time), elapsed_time)
                    else:
                        # Scanning got slower.
                        log('\t\t\t\t: Scanned for %.1f"' % elapsed_time)

                    if detected_in_span:
                        failure_count = 0
                        detected_in_span = False  # Turn off the switch for the later use.
                    else:
                        failure_count += 1
                        report += '\tNothing over a span of %d.' % scanning_url_span
                        report += '\tConsecutive failures: %i' % failure_count
                        print(report)

                else:  # Failure count reached the limit. Something went wrong.
                    somethings_wrong = True
                    loop_span = int(__get_elapsed_sec(first_trial_time) / 60)
                    log('Warning: Failed %d times in a row for %d minutes.' % (MAX_FAILURE, loop_span))
                    trim_logs(Constants.LOG_PATH)
        except Exception as main_loop_exception:
            log('Error: %s\n[Traceback]\n%s' % (main_loop_exception, traceback.format_exc()))
