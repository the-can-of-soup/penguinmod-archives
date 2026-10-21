# IMPORTS

from __future__ import annotations

import os

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
LIGHT_REQUEST_MAX_SIMULTANEOUS: int = 4
HEAVY_REQUEST_DELAY: float = 10.0
HEAVY_REQUEST_BACKOFF_FACTOR: float = 1.5
HEAVY_REQUEST_MAX_RETRIES: int = 3
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

    :param method: Request method.
    :type method: str
    :param url: Request URL.
    :type url: str
    :param params: URL parameters for the request.
    :type params: dict[str, str] | None
    :param data: JSON POST data for the request.
    :type data: dict[str, Any] | None
    :param max_retries: Maximum number of times to retry the fetch.
    :type max_retries: int
    :param initial_retry_delay: Delay between the first attempt failing and starting a second attempt.
    :type initial_retry_delay: float
    :param backoff_factor: Factor to multiply the retry delay by on each subsequent attempt.
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


# noinspection bad-assignment, unresolved-references
def main() -> None:

    # START

    print('PENGUINMOD METADATA ARCHIVES')
    print('============================')
    print('')

    last_snapshot_path: str | None = input('Path of previous snapshot file (empty to'
        + ' create an absolute snapshot; only put trusted files here): ').strip()
    print('')
    if last_snapshot_path == '':
        last_snapshot_path = None
    if last_snapshot_path is not None:
        assert os.path.isfile(last_snapshot_path)

    input('Press ENTER to take a snapshot of ALL available project and user metadata on'
        + ' PenguinMod.\nThis will take a very, VERY long time.')

    snapshot = MetadataSnapshot()
    snapshot.start()


    # All page counts here are estimates and may be exceeded or not reached.


    # STAGE 1: GENERAL DATA

    print('\033[2J\033[3J\033[H', end='') # Clear terminal
    print('STAGE 1/5: GENERAL DATA')
    print('-----------------------')

    general_data: JSONSnapshot = fetch('GET', f'{API_ROOT}/api/v1/misc/getStats',
        critical=True, status_prefix='\033[3;1H\033[0J') # Line 3 (clear to end of screen)
    snapshot.add_general_data(general_data)

    user_count: int = general_data.data['userCount']
    project_count: int = general_data.data['projectCount']


    # STAGE 2: DISCOVER USERS

    print('\033[2J\033[3J\033[H', end='') # Clear terminal
    print('STAGE 2/5: DISCOVER USERS')
    print('-------------------------')

    progress_bar = tqdm.tqdm(
        total=user_count, unit='user', desc='Progress', leave=True,
    )

    user_page_count: int = math.ceil(user_count / EXPECTED_PAGE_SIZE)

    page_idx: int = 0
    while True:
        response = fetch(
            'GET', f'{API_ROOT}/api/v1/projects/searchusers',
            params={'page': str(page_idx), 'query': ''},
            status_prefix='\033[4;1H\033[0K', # Line 4
            initial_retry_delay=HEAVY_REQUEST_DELAY,
            backoff_factor=HEAVY_REQUEST_BACKOFF_FACTOR,
            max_retries=HEAVY_REQUEST_MAX_RETRIES,
            critical=True,
        )
        assert isinstance(response.data, list)

        page_usernames: list[str] = []
        for user in response.data:
            snapshot.add_user(user['id'], JSONSnapshot(user['username'], timestamp_override=response.timestamp))
            page_usernames.append(user['username'])

        # Line 3
        sys.stdout.write('\033[3;1H\033[0K') ; sys.stdout.flush()
        progress_bar.update(len(response.data))

        # Line 5 (clear to end of screen)
        if len(response.data) > 0:
            print(f'\033[5;1H\033[0JUsers on page {page_idx+1}/{user_page_count}: {", ".join(page_usernames)}')
        else:
            print(f'\0335;1H\033[0JCompleted')

        # Line 4
        countdown(HEAVY_REQUEST_DELAY, prefix='\033[4;1H\033[0KWaiting... ')

        # TODO: remove testing
        # if page_idx >= 1:
        #     break

        if len(response.data) == 0:
            break
        page_idx += 1

    # Line 3
    sys.stdout.write('\033[3;1H\033[0K') ; sys.stdout.flush()
    progress_bar.close()


    # noinspection unused-parameter
    def allow_404_validator(response: requests.Response, json_data: JSON) -> None:
        if response.status_code == 404:
            # User doesn't exist or is banned; not a fetching error
            return

        response.raise_for_status()

    # noinspection unused-parameter
    def allow_404_403_validator(response: requests.Response, json_data: JSON) -> None:
        if response.status_code in (404, 403):
            # User doesn't exist, is banned, or has a private profile; not a fetching error
            return

        response.raise_for_status()


    # STAGE 3: USER PROFILE DATA
    # TODO: implement multiple simultaneous requests

    print('\033[2J\033[3J\033[H', end='')  # Clear terminal
    print('STAGE 3/5: USER PROFILE DATA')
    print('----------------------------')

    progress_bar = tqdm.tqdm(
        desc='Progress', total=len(snapshot.usernames), unit='user', leave=True,
    )

    total_follower_page_count: int = 0

    for user_idx, user_id in enumerate(snapshot.usernames):
        username: str = snapshot.usernames[user_id].data

        response = fetch(
            'GET', f'{API_ROOT}/api/v1/users/profile',
            params={'target': username}, status_prefix='\033[4;1H\033[0K', # Line 4
            validator=allow_404_validator,
            critical=True, # I want to capture every user
        )
        snapshot.add_user_profile(user_id, response)

        if 'followers' in response.data:
            # noinspection unsupported-operator
            total_follower_page_count += math.ceil(
                response.data['followers'] / EXPECTED_PAGE_SIZE
            )

        # Line 3
        sys.stdout.write('\033[3;1H\033[0K') ; sys.stdout.flush()
        progress_bar.update(1)

        # Line 5 (clear to end of screen)
        print(f'\033[5;1H\033[0JFetched profile of user {username} ({user_id})')

    # Line 3
    sys.stdout.write('\033[3;1H\033[0K') ; sys.stdout.flush()
    progress_bar.close()


    # STAGE 4: FOLLOWERS

    print('\033[2J\033[3J\033[H', end='')  # Clear terminal
    print('STAGE 4/5: FOLLOWERS')
    print('--------------------')

    progress_bar = tqdm.tqdm(
        desc='Progress', total=total_follower_page_count, unit='page', leave=True,
    )

    for user_id, username_snapshot in snapshot.usernames.items():
        username: str = username_snapshot.data
        profile_data = snapshot.user_profiles[user_id].data

        follower_page_count_str: str = '?'
        if 'followers' in profile_data and profile_data.get('success') is True:
            # noinspection unsupported-operator
            follower_page_count_str = str(math.ceil(
                profile_data['followers'] / EXPECTED_PAGE_SIZE
            ))

        followers: list[JSON] | None = []

        page_idx: int = 0
        while True:
            # Line 4
            print(f'\033[4;1H\033[0KUser {username} ({user_id}) page {page_idx+1}/{follower_page_count_str}')

            response = fetch(
                'GET', f'{API_ROOT}/api/v1/users/meta/getfollowers',
                params={'username': username, 'page': str(page_idx)},
                status_prefix='\033[5;1H\033[0K', # Line 5
                validator=allow_404_validator,
                critical=True, # I want to capture every follower and am too lazy to properly handle errors caused by max retries being exceeded
            )

            if isinstance(response.data, dict) and 'error' in response.data:
                # User is banned or does not exist
                followers = None
                break
            assert isinstance(response.data, list)
            followers.extend(response.data)

            if len(response.data) == 0:
                break

            # Line 3
            sys.stdout.write('\033[3;1H\033[0K') ; sys.stdout.flush()
            progress_bar.update(1)

            # Line 6 (clear to end of screen)
            print(f'\033[6;1H\033[0JFollowers of {username} page {page_idx+1}/{follower_page_count_str}:'
                + f' {", ".join(follower['username'] for follower in response.data)}')

            page_idx += 1

        if followers is not None:
            snapshot.add_user_followers(user_id, JSONSnapshot(followers))

    # Line 3
    sys.stdout.write('\033[3;1H\033[0K') ; sys.stdout.flush()
    progress_bar.close()


    # STAGE 5: PROJECT METADATA

    print('\033[2J\033[3J\033[H', end='') # Clear terminal
    print('STAGE 5/5: PROJECT METADATA')
    print('---------------------------')

    progress_bar = tqdm.tqdm(
        desc='Progress', total=project_count, unit='project', leave=True,
    )

    for user_id, username_snapshot in snapshot.usernames.items():
        username: str = username_snapshot.data

        page_idx: int = 0
        while True:
            # Line 4
            print(f'\033[4;1H\033[0KUser {username} ({user_id}) page {page_idx+1}')

            response = fetch(
                'GET', f'{API_ROOT}/api/v1/projects/getprojectsbyauthor',
                params={'authorUsername': username, 'page': str(page_idx)},
                status_prefix='\033[5;1H\033[0K', # Line 5
                validator=allow_404_403_validator,
                critical=True, # I want to capture every project
            )

            if isinstance(response.data, dict) and 'error' in response.data:
                # User is banned, does not exist, or has a private profile
                break
            assert isinstance(response.data, list)

            for project in response.data:
                snapshot.add_project_id(project['id'])
                snapshot.add_project_metadata(project['id'], JSONSnapshot(project))

            if len(response.data) == 0:
                break

            # Line 3
            sys.stdout.write('\033[3;1H\033[0K') ; sys.stdout.flush()
            progress_bar.update(len(response.data))

            # Line 6 (clear to end of screen)
            print(f'\033[6;1H\033[0J{len(response.data)} project{"" if len(response.data) == 1 else "s"} on {username} page {page_idx+1}')

            page_idx += 1

    # Line 3
    sys.stdout.write('\033[3;1H\033[0K') ; sys.stdout.flush()
    progress_bar.close()


    # END

    print('\033[2J\033[3J\033[H', end='')  # Clear terminal
    print('PENGUINMOD METADATA ARCHIVES')
    print('============================')
    print('')

    last_snapshot: MetadataSnapshot | None = None

    if last_snapshot_path is not None:
        print('Loading snapshot chain...', end='')
        # noinspection broad-exception
        try:
            last_snapshot = MetadataSnapshot.load_from_file(last_snapshot_path)
        except:
            print('\rFAILED TO LOAD SNAPSHOT CHAIN')
            print('=============================')
            traceback.print_exc()
            print('=============================')
            print('The absolute snapshot will be saved as-is instead.')
        else:
            print(f'\rSnapshot chain loaded from {last_snapshot_path!r}'.ljust(29))

    if last_snapshot is not None:
        print('Resolving snapshot chain diffs...', end='')
        last_snapshot: MetadataSnapshot = last_snapshot.resolve()

        print('\rComputing diff for this snapshot...', end='')
        snapshot = snapshot.difference(last_snapshot)

        print('\rComputed diff for this snapshot'.ljust(36))

    print('Saving...', end='')
    snapshot.save_to_file()
    assert snapshot.file_path is not None
    snapshot_size: int = os.stat(snapshot.file_path).st_size
    print(f'\rSnapshot written to {snapshot.file_path!r} ({snapshot_size:,} bytes)')

    snapshot.finish()

    assert snapshot.start_time is not None and snapshot.end_time is not None
    time_elapsed: float = snapshot.end_time - snapshot.start_time
    print(f'Snapshot completed in {int(time_elapsed//(24*3600))}d,{int(time_elapsed//3600%24)}h,{int(time_elapsed//60%60)}m,{time_elapsed%60:.3f}s!')

    print('')
    input('Press ENTER to exit.')


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
        input('Press ENTER to exit.')
        sys.exit(1)
