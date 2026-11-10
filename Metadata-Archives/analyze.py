from collections.abc import Callable
import sys

import snapshot



def project_id_stats(snapshot_: snapshot.MetadataSnapshot) -> None:
    numerical_project_ids: list[str] = [i for i in snapshot_.projects if i.isdigit()]

    print(f'Smallest numerical project ID: {min(numerical_project_ids)}')
    print(f'Largest numerical project ID: {max(numerical_project_ids)}')

    max_consecutive_digits: int = 0
    max_consecutive_digits_ids: list[str] = []
    for project_id in numerical_project_ids:
        consecutive: int = 0
        character: str | None = None
        max_consecutive: int = 0
        for c in project_id:
            if c == character:
                consecutive += 1
            else:
                if consecutive > max_consecutive:
                    max_consecutive = consecutive
                consecutive = 1
                character = c
        if consecutive > max_consecutive:
            max_consecutive = consecutive

        if max_consecutive >= max_consecutive_digits:
            if max_consecutive > max_consecutive_digits:
                max_consecutive_digits_ids = []
            max_consecutive_digits = max_consecutive
            max_consecutive_digits_ids.append(project_id)

    print(f'IDs with the most consecutive digits: {', '.join(max_consecutive_digits_ids)}')
    print(f'Non-numerical project IDs: {', '.join(i for i in snapshot_.projects if not i.isdigit())}')



OPTIONS: dict[str, Callable[[snapshot.MetadataSnapshot], None]] = {
    'project-id-stats': project_id_stats,
}



if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('First argument options:')
        print('\n'.join(f'  {o}' for o in OPTIONS))
        sys.exit(0)
    elif sys.argv[1] not in OPTIONS:
        print(f'Invalid option {sys.argv[1]!r}; run with no arguments for option list')
        sys.exit(2)

    if len(sys.argv) < 3:
        print('Please provide the snapshot file path as the second argument (only use files you trust)')
        sys.exit(2)

    snapshot_: snapshot.MetadataSnapshot = snapshot.MetadataSnapshot.load_from_file(sys.argv[2])
    OPTIONS[sys.argv[1]](snapshot_)
