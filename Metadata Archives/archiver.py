from __future__ import annotations

from snapshot import JSONSnapshot, MetadataSnapshot
from typing import Any
import threading
import traceback
import requests
import tqdm
import time
import math
import sys

BASE_URL: str = 'https://projects.penguinmod.com'
MAX_SIMULTANEOUS_LIGHT_REQUESTS: int = 4
HEAVY_REQUEST_DELAY: float = 10.0
EXPECTED_PAGE_SIZE: int = 20 # Page size used in search APIs

# APIS USED BY THIS PROGRAM
#
# - /api/v1/misc/getStats
# - /api/v1/projects/searchusers?query=&page=<PAGE_INDEX>
# - /api/v1/users/profile?target=<USERNAME>
# - /api/v1/users/meta/getfollowers?username=<USERNAME>&page=<PAGE_INDEX>
# - /api/v1/projects/searchprojects?type=newest&reverse=true&query=&page=<PAGE_INDEX>
# - /api/v1/projects/getproject?requestType=metadata&projectID=<PROJECT_ID>

def fetch(method: str, url: str, params: dict[str, str] | None = None, data: dict[str, Any] | None = None,
          max_retries: int = 5, initial_retry_delay: float = 1.0, backoff_factor: float = 1.7, critical: bool = False,
          status_prefix: str = '') -> JSONSnapshot:
    response: requests.Response
    last_exception: Exception = RuntimeError('Did not attempt fetch')

    i = 0
    while i <= max_retries:
        if i == 0:
            sys.stdout.write(status_prefix + f'Fetching...')
        else:
            sys.stdout.write(status_prefix + f'Fetching (retry {i})...')
        sys.stdout.flush()

        # Send request
        try:
            response = requests.request(method, url, params=params, json=data)
            response.raise_for_status()
            return JSONSnapshot(response.json())
        except requests.RequestException as exc:
            last_exception = exc

        # Exponential backoff
        if i != max_retries:
            delay: float = initial_retry_delay * backoff_factor ** i
            countdown(delay, prefix=status_prefix + 'Retrying in ', suffix=' seconds...')

        if critical:
            input(status_prefix + f'Fetch failed max of {max_retries+1} times with error:\n{type(last_exception).__name__}: {last_exception}\nPress ENTER to try again.')
        else:
            i += 1

    return JSONSnapshot(None, failure_message=f'Error during fetch: {type(last_exception).__name__}: {last_exception}')

def countdown(duration: float, prefix: str = '', suffix: str = '') -> None:
    start_time: float = time.time()
    while True:
        now: float = time.time()
        if now - start_time >= duration:
            return
        sys.stdout.write(prefix + f'{duration - (now - start_time):.1f}' + suffix)
        sys.stdout.flush()
        time.sleep(0.05)

def main() -> None:
    print('PENGUINMOD METADATA ARCHIVES')
    print('============================')
    print('')
    input('Press ENTER to take a snapshot.\nThis will take a very, VERY long time.')

    snapshot = MetadataSnapshot()
    snapshot.start()

    # STAGE 1: GENERAL DATA

    print('\033[2J\033[3J\033[H', end='') # Clear terminal
    print('STAGE 1: GENERAL DATA')
    print('---------------------')

    general_data: JSONSnapshot = fetch('GET', BASE_URL + '/api/v1/misc/getStats',
        critical=True, status_prefix='\033[3;1H\033[0J') # Line 3 (clear to end of screen)
    snapshot.add_general_data(general_data)

    user_count: int = general_data.data['userCount']
    project_count: int = general_data.data['projectCount']

    # STAGE 2: FIND USERNAMES

    print('\033[2J\033[3J\033[H', end='') # Clear terminal
    print('STAGE 2: FIND USERNAMES')
    print('-----------------------')

    progress_bar = tqdm.tqdm(total=user_count, unit='users')

    user_page_count: int = math.ceil(user_count / EXPECTED_PAGE_SIZE)
    # user_page_count: int = 5 # Testing

    for page_idx in range(user_page_count):
        response = fetch('GET', BASE_URL + '/api/v1/projects/searchusers',
            params={'page': page_idx, 'query': ''}, status_prefix='\033[4;1H\033[0K', # Line 4
            max_retries=3, initial_retry_delay=10.0, backoff_factor=1.5, critical=True)

        page_usernames: list[str] = []
        for user in response.data:
            snapshot.add_user_id(user['id'])
            page_usernames.append(user['username'])

        sys.stdout.write('\033[3;1H\033[0K') ; sys.stdout.flush() # Line 3
        progress_bar.update(len(response.data))

        print(f'\033[5;1H\033[0JUsernames on page {page_idx+1}: ' + (', '.join(page_usernames)))  # Line 5 (clear to end of screen)

        countdown(HEAVY_REQUEST_DELAY, prefix='\033[4;1H\033[0KWaiting... ') # Line 4

    sys.stdout.write('\033[3;1H\033[0K') ; sys.stdout.flush() # Line 3
    progress_bar.close()

    # snapshot.save_to_file() # Testing
    input('TODO')

if __name__ == '__main__':
    try:
        main()
    except:
        print('AN UNEXPECTED ERROR OCCURRED')
        print('============================')
        traceback.print_exc()
        print('============================')
        print('')
        input('Press ENTER to close.')

