# IMPORTS

from __future__ import annotations

from snapshot import JSONSnapshot, MetadataSnapshot, JSON
from typing import Any, Callable
import traceback
import requests
import tqdm
import time
import math
import sys



# CONSTANTS

API_ROOT: str = 'https://projects.penguinmod.com'
MAX_SIMULTANEOUS_LIGHT_REQUESTS: int = 4
HEAVY_REQUEST_DELAY: float = 10.0
EXPECTED_PAGE_SIZE: int = 20 # Page size used in search APIs



# APIS USED BY THIS PROGRAM
#
# 1. GET /api/v1/misc/getStats
# 2. GET /api/v1/projects/searchusers?query=&page=<PAGE_INDEX>
# 3. GET /api/v1/users/profile?target=<USERNAME>
#    - HTTP 404 {"error": "NotFound"} if user doesn't exist or is banned
#    - HTTP 200 {"success": false, ...} if profile is private
# 4. GET /api/v1/users/meta/getfollowers?username=<USERNAME>&page=<PAGE_INDEX>
#    - HTTP 404 {"error": "User not found"} if user doesn't exist or is banned
# 5. GET /api/v1/projects/getprojectsbyauthor?authorUsername=<USERNAME>&page=<PAGE_INDEX>
#    - HTTP 404 {"error": "User not found"} if user doesn't exist or is banned
#    - HTTP 403 {"error": "PrivateProfile"} if user's profile is set to private



# DEFINITIONS


def fetch(
        method: str, url: str, params: dict[str, str] | None = None, data: dict[str, Any] | None = None,
        max_retries: int = 5, initial_retry_delay: float = 1.0, backoff_factor: float = 1.7, critical: bool = False,
        status_prefix: str = '',
        validator: Callable[[requests.Response, JSON], None] = lambda response, snapshot: response.raise_for_status(),
    ) -> JSONSnapshot:
    """
    Fetches from an HTTP JSON API.

    :param method: The request method.
    :type method: str
    :param url: The request URL.
    :type url: str
    :param params: URL parameters for the request.
    :type params: dict[str, str] | None
    :param data: JSON POST data for the request.
    :type data: dict[str, Any] | None
    :param max_retries: The maximum number of times to retry the fetch.
    :type max_retries: int
    :param initial_retry_delay: The delay between the first attempt failing and starting a second attempt.
    :type initial_retry_delay: float
    :param backoff_factor: The factor to multiply the retry delay by on each subsequent attempt.
    :type backoff_factor: float
    :param critical: If True, failing all retries will wait for a user input and then try all over again, instead of returning.
    :type critical: bool
    :param status_prefix: String to be prepended to every status update written to standard output.
    :type status_prefix: str
    :param validator: Function that should accept a ``requests.Response`` object and JSON from an attempt response and raise ``requests.exceptions.RequestException`` if the attempt should be considered "failed". If omitted, the default validator will raise if the response status code was not success.
    :type validator: Callable[[requests.Response, JSON], None]
    :return:
    """
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
            json_data = response.json()
            validator(response, json_data)
            return JSONSnapshot(json_data)
        except requests.exceptions.RequestException as exc:
            last_exception = exc

        # Exponential backoff
        if i != max_retries:
            delay: float = initial_retry_delay * backoff_factor ** i
            countdown(delay, prefix=status_prefix + 'Retrying in ', suffix=' seconds...')

        if critical:
            # input(status_prefix + f'Fetch failed max of {max_retries+1} times with error:\n{type(last_exception).__name__}: {last_exception}\nPress ENTER to try again.')
            input(status_prefix + f'Fetch failed max of {max_retries+1} times; press ENTER to try again.')
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



# MAIN


# noinspection bad-assignment, unresolved-references, unused-local
def main() -> None:
    print('PENGUINMOD METADATA ARCHIVES')
    print('============================')
    print('')
    input('Press ENTER to take a snapshot of ALL available project and user metadata on'
        + ' PenguinMod.\nThis will take a very, VERY long time.')

    snapshot = MetadataSnapshot()
    snapshot.start()


    # STAGE 1: GENERAL DATA

    print('\033[2J\033[3J\033[H', end='') # Clear terminal
    print('STAGE 1/6: GENERAL DATA')
    print('-----------------------')

    general_data: JSONSnapshot = fetch('GET', API_ROOT + '/api/v1/misc/getStats',
                                       critical=True, status_prefix='\033[3;1H\033[0J') # Line 3 (clear to end of screen)
    snapshot.add_general_data(general_data)

    user_count: int = general_data.data['userCount']
    project_count: int = general_data.data['projectCount']


    # STAGE 2: FIND USERNAMES

    print('\033[2J\033[3J\033[H', end='') # Clear terminal
    print('STAGE 2/6: FIND USERNAMES')
    print('-------------------------')

    progress_bar = tqdm.tqdm(total=user_count, unit='user', desc='Progress:')

    user_page_count: int = math.ceil(user_count / EXPECTED_PAGE_SIZE)
    # user_page_count: int = 5 # TODO: remove testing

    for page_idx in range(user_page_count):
        response = fetch(
            'GET', API_ROOT + '/api/v1/projects/searchusers',
            params={'page': str(page_idx), 'query': ''}, status_prefix='\033[4;1H\033[0K', # Line 4
            max_retries=3, initial_retry_delay=HEAVY_REQUEST_DELAY, backoff_factor=1.5,
            critical=True,
        )
        assert isinstance(response.data, list)

        page_usernames: list[str] = []
        for user in response.data:
            snapshot.add_user(user['id'], JSONSnapshot(user['username'], timestamp_override=response.timestamp))
            page_usernames.append(user['username'])

        sys.stdout.write('\033[3;1H\033[0K') ; sys.stdout.flush() # Line 3
        progress_bar.update(len(response.data))

        print(f'\033[5;1H\033[0JUsernames on page {page_idx+1}: ' + (', '.join(page_usernames)))  # Line 5 (clear to end of screen)

        countdown(HEAVY_REQUEST_DELAY, prefix='\033[4;1H\033[0KWaiting... ') # Line 4

    sys.stdout.write('\033[3;1H\033[0K') ; sys.stdout.flush() # Line 3
    progress_bar.close()


    # STAGE 3: USER PROFILES
    # TODO: implement multiple simultaneous requests

    print('\033[2J\033[3J\033[H', end='')  # Clear terminal
    print('STAGE 3/6: USER PROFILES')
    print('------------------------')

    progress_bar = tqdm.tqdm(total=user_count, unit='user', desc='Progress:')

    # noinspection unused-parameter
    def stage_3_validator(response: requests.Response, json_data: JSON) -> None:
        if response.status_code == 404:
            return # User doesn't exist or is banned; not a fetching error
        response.raise_for_status()

    user_idx: int = 0
    for user_id in snapshot.usernames:
        username: str = snapshot.usernames[user_id].data

        response = fetch(
            'GET', API_ROOT + '/api/v1/users/profile',
            params={'target': username}, status_prefix='\033[4;1H\033[0K', # Line 4
            validator=stage_3_validator, critical=True, # Not actually critical, but I want to capture every user
        )
        snapshot.add_user_profile(user_id, response)

        sys.stdout.write('\033[3;1H\033[0K') ; sys.stdout.flush() # Line 3
        progress_bar.update(1)

        print(f'\033[5;1H\033[0JFetched profile of user {user_idx+1} ({username})') # Line 5 (clear to end of screen)

        user_idx += 1

    # snapshot.save_to_file() # TODO: remove testing
    input('TODO')
    snapshot.finish()


if __name__ == '__main__':
    # noinspection broad-exception
    try:
        main()
    except:
        print('AN UNEXPECTED ERROR OCCURRED')
        print('============================')
        traceback.print_exc()
        print('============================')
        print('')
        input('Press ENTER to close.')
