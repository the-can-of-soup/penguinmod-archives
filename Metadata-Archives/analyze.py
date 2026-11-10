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

    print(f'IDs with the most consecutive digits: {max_consecutive_digits_ids!r}')
    print(f'Non-numerical project IDs: {[i for i in snapshot_.projects if not i.isdigit()]!r}')

    least_unique_digits: int | None = None
    least_unique_digits_projects: list[str] = []
    for project_id in numerical_project_ids:
        unique_digits: int = 0
        digits: set[str] = set()
        for c in project_id:
            if c not in digits:
                unique_digits += 1
            digits.add(c)

        if least_unique_digits is None or unique_digits <= least_unique_digits:
            if least_unique_digits is None or unique_digits < least_unique_digits:
                least_unique_digits_projects = []
            least_unique_digits = unique_digits
            least_unique_digits_projects.append(project_id)

    print(f'IDs with the least unique digits ({least_unique_digits}): {least_unique_digits_projects!r}')


def project_stats(snapshot_: snapshot.MetadataSnapshot) -> None:
    max_title_len: int = 0
    max_titles: dict[str, str] = {}
    max_instr_len: int = 0
    max_instrs: dict[str, str] = {}
    max_notes_len: int = 0
    max_notes: dict[str, str] = {}
    max_instr_plus_notes_len: int = 0
    max_instrs_plus_notes: dict[str, tuple[str, str]] = {}
    max_loves: int = 0
    max_loves_project: str | None = None
    max_votes: int = 0
    max_votes_project: str | None = None
    max_views: int = 0
    max_views_project: str | None = None
    max_impressions: int = 0
    max_impressions_project: str | None = None
    for id_, project_snapshot in snapshot_.projects.items():
        assert project_snapshot is not None
        project = project_snapshot.data

        if 'title' in project:
            title: str = project['title']
            len_: int = len(title)
            if len_ >= max_title_len:
                if len_ > max_title_len:
                    max_titles = {}
                max_title_len = len_
                max_titles[id_] = title

        if 'instructions' in project:
            instr: str = project['instructions']
            len_: int = len(instr)
            if len_ >= max_instr_len:
                if len_ > max_instr_len:
                    max_instrs = {}
                max_instr_len = len_
                max_instrs[id_] = instr

        if 'notes' in project:
            notes: str = project['notes']
            len_: int = len(notes)
            if len_ >= max_notes_len:
                if len_ > max_notes_len:
                    max_notes = {}
                max_notes_len = len_
                max_notes[id_] = notes

        if 'instructions' in project and 'notes' in project:
            instr: str = project['instructions']
            notes: str = project['notes']
            len_: int = len(instr) + len(notes)
            if len_ >= max_instr_plus_notes_len:
                if len_ > max_instr_plus_notes_len:
                    max_instrs_plus_notes = {}
                max_instr_plus_notes_len = len_
                max_instrs_plus_notes[id_] = (instr, notes)

        loves: int = project.get('loves', 0)
        votes: int = project.get('votes', 0)
        views: int = project.get('views', 0)
        impressions: int = project.get('impressions', 0)
        if loves > max_loves: max_loves = loves; max_loves_project = id_
        if votes > max_votes: max_votes = votes; max_votes_project = id_
        if views > max_views: max_views = views; max_views_project = id_
        if impressions > max_impressions:
            max_impressions = impressions; max_impressions_project = id_


    print(f'Projects with longest titles ({max_title_len} characters): {list(max_titles.keys())!r}')
    print(f'Projects with longest instructions ({max_instr_len} characters): {list(max_instrs.keys())!r}')
    print(f'Projects with longest notes ({max_notes_len} characters): {list(max_notes.keys())!r}')
    print(f'Projects with longest instructions + notes ({max_instr_plus_notes_len} combined characters): {list(max_instrs_plus_notes.keys())!r}')
    print('Projects with the most:')
    print(f'  Likes: {max_loves_project} ({max_loves:,})')
    print(f'  Votes: {max_votes_project} ({max_votes:,})')
    print(f'  Views: {max_views_project} ({max_views:,})')
    print(f'  Impressions: {max_impressions_project} ({max_impressions:,})')



OPTIONS: dict[str, Callable[[snapshot.MetadataSnapshot], None]] = {
    'project-id-stats': project_id_stats,
    'project-stats': project_stats,
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
