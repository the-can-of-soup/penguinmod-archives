from __future__ import annotations

import abc
from abc import abstractmethod, ABCMeta
from typing import Any, Union, Self
from collections import OrderedDict
import time

JSON = Union[dict, list, str, float, bool, None]

class AbstractSingleton(metaclass=ABCMeta):
    """
    Parent type for singleton types.
    """
    _instance: Self | None = None

    def __new__(cls, *args, **kwargs) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return f'{self.singleton_name()}'

    def __str__(self) -> str:
        return repr(self)

    @abc.abstractmethod
    def singleton_name(self) -> str:
        """
        Return the name of the singleton.

        :return: The name of the singleton.
        :rtype: str
        """

class UnchangedJSONType(AbstractSingleton):
    """
    Type for UnchangedJSON singleton.
    """
    def singleton_name(self) -> str:
        return 'UnchangedJSON'

UnchangedJSON = UnchangedJSONType()

class DeletedKeyType(AbstractSingleton):
    """
    Type for DeletedKey singleton.
    """
    def singleton_name(self) -> str:
        return 'DeletedKey'

DeletedKey = DeletedKeyType()

def json_difference(new: JSON, old: JSON) -> JSON | UnchangedJSONType:
    """
    Returns the difference between two JSON values.
    This is used to optimize storing revisions.

    This process is not commutative.

    :param new: The newer JSON value.
    :type new: JSON
    :param old: The older JSON value.
    :type old: JSON
    :return: The difference between the values.
    :rtype: JSON | UnchangedJSONType
    """
    if type(new) is not type(old):
        return new

    if isinstance(new, dict):
        difference: dict = {}
        for key in new:
            if key not in old:
                difference[key] = new[key]
            else:
                key_difference = json_difference(new[key], old[key])
                if key_difference is not UnchangedJSON:
                    difference[key] = key_difference
        for key in old: # TODO: Fix "new" being set to "difference" by mistake
            if key not in new:
                difference[key] = DeletedKey
        if len(difference) == 0:
            return UnchangedJSON
        return difference

    elif isinstance(new, list):
        if len(new) > len(old):
            if new[:len(old)] != old:
                return new # Not just elements added to the end of list; return the entire new dict
            return [UnchangedJSON] * len(old) + new[len(old):]
        elif len(new) < len(old):
            return new # Elements removed from the list; return the entire new list
        difference: list = []
        different: bool = False
        for i in range(len(new)):
            new_value: JSON = new[i]
            old_value: JSON = old[i]
            value_difference = json_difference(new_value, old_value)
            difference.append(value_difference)
            if value_difference is not UnchangedJSON:
                different = True
        if different:
            return difference
        return UnchangedJSON

    elif new == old:
        return UnchangedJSON

    return new # Cannot take difference for this type; return the entire new value

def json_reverse_difference(old: JSON, difference: JSON | UnchangedJSONType) -> JSON:
    """
    Reverses ``json_difference()``.

    This process is not commutative.

    :param old: The older JSON value.
    :type old: JSON
    :param difference: The difference between the values.
    :type difference: JSON | UnchangedJSONType
    :return: The newer JSON value.
    :rtype: JSON
    """
    if difference is UnchangedJSON:
        return old
    if type(difference) is not type(old):
        return difference

    if isinstance(difference, dict):
        new: dict = old.copy()
        for key in difference:
            if difference[key] is DeletedKey:
                del new[key]
            new[key] = difference[key]
        return new

    elif isinstance(difference, list):
        if len(difference) > len(old):
            return old + difference[len(old):]
        elif len(difference) < len(old):
            return difference # Difference is smaller than old list; difference is just the new value
        new: list = []
        for i in range(len(difference)):
            old_value: JSON = old[i]
            value_difference: JSON | UnchangedJSONType = difference[i]
            new_value: JSON = json_reverse_difference(old_value, value_difference)
            new.append(new_value)
        return new

    return difference # Cannot take difference for this type; difference is just the new value

class AbstractSnapshot(metaclass=ABCMeta):
    """
    Parent type for snapshots.
    """
    def __init__(self, last_snapshot: Self):
        """
        :param last_snapshot: The snapshot before this one.
        """
        self._last_snapshot: Self | None = last_snapshot

        # Public attributes are pickled
        self.is_relative: bool = self._last_snapshot is not None

    def __getstate__(self) -> dict[str, Any]:
        attributes: dict[str, Any] = self.__dict__.copy()
        return {i: attributes[i] for i in attributes if not i.startswith('_')}

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)
        # TODO: Set _last_snapshot to contents of last snapshot if self.is_relative is True

    def __repr__(self) -> str:
        if self.is_relative:
            return f'<{type(self).__name__}(last_snapshot={self._last_snapshot}) at {id(self)}>'
        return f'<{type(self).__name__}(last_snapshot=None) at {id(self)}>'

    def __str__(self) -> str:
        return repr(self)

    @abstractmethod
    def overlay(self, below: Self) -> Self:
        """
        Overlays this snapshot on top of an absolute snapshot.

        :param below: The absolute snapshot to be overlaid (the older snapshot).
        :type below: Self
        :return: The composite snapshot.
        :rtype: Self
        """

    @abstractmethod
    def difference(self, below: Self) -> Self:
        """
        Creates a relative snapshot that is the difference between this snapshot and another snapshot.
        Both snapshots must be absolute.

        :param below: The older absolute snapshot.
        :type below: Self
        :return: The difference as a relative snapshot.
        :rtype: Self
        """

    def resolve(self) -> Self:
        """
        Creates an absolute snapshot by combining all relative snapshots.

        :return: The absolute snapshot.
        :rtype: Self
        """
        if self.is_relative:
            return self.overlay(self._last_snapshot.resolve())
        return self

class JSONSnapshot(AbstractSnapshot):
    """
    A JSON response from an API.
    Might only include changes from the previous snapshot.
    """
    def __init__(self, data: JSON | UnchangedJSONType = UnchangedJSON, failure_message: str | None = None, last_snapshot: JSONSnapshot | None = None):
        super().__init__(last_snapshot)

        # Public attributes are pickled
        self.data: JSON | UnchangedJSONType = UnchangedJSON
        self.failure_message: str | None = failure_message
        self.timestamp: float = time.time()

        # Handle failed snapshots
        if self.failure_message is not None:
            return

        # Handle initial snapshot
        if self._last_snapshot is None:
            self.data = data
            return

        # Use JSON difference
        self.data = json_difference(data, last_snapshot.data)

    def overlay(self, below: Self) -> Self:
        if below.is_relative:
            raise ValueError('"below" must be an absolute snapshot')
        if not self.is_relative:
            return self

        return JSONSnapshot(
            data=json_reverse_difference(self._last_snapshot.data, self.data),
            failure_message=self.failure_message,
            last_snapshot=None,
        )

    def difference(self, below: Self) -> Self:
        if below.is_relative:
            raise ValueError('"below" must be an absolute snapshot')
        if self.is_relative:
            raise ValueError('"difference()" may only be called on absolute snapshots')

        return JSONSnapshot(
            data=json_difference(self.data, below.data),
            failure_message=self.failure_message,
            last_snapshot=below,
        )

    def set_time(self) -> None:
        """
        Sets the time of the snapshot to the current time.
        If never called, the snapshot time will be the time that ``__init__()`` was called.

        :rtype: None
        """
        self.timestamp = time.time()

class DatabaseSnapshot(AbstractSnapshot):
    """
    The state of the metadata for all users and projects at a given time.
    Might only include changes from the previous snapshot.
    """
    def __init__(self, last_snapshot: DatabaseSnapshot | None = None) -> None:
        """
        :param last_snapshot: The snapshot before this one.
        """
        super().__init__(last_snapshot)

        # Public attributes are pickled
        self.removed_users: set[str] = set()
        self.removed_projects: set[str] = set()
        self.general_data: JSONSnapshot | None = None
        self.user_profiles: OrderedDict[str, JSONSnapshot | None] = OrderedDict()
        self.user_followers: OrderedDict[str, JSONSnapshot | None] = OrderedDict()
        self.projects: OrderedDict[str, JSONSnapshot | None] = OrderedDict()
        self.start_time: float | None = None
        self.end_time: float | None = None

        if self.is_relative:
            # noinspection PyUnresolvedReferences
            self.removed_users = set(self._last_snapshot.user_profiles.keys())
            # noinspection PyUnresolvedReferences
            self.removed_projects = set(self._last_snapshot.user_followers.keys())

    def overlay(self, below: Self) -> Self:
        if below.is_relative:
            raise ValueError('"below" must be an absolute snapshot')
        if not self.is_relative:
            return self

        composite = DatabaseSnapshot(last_snapshot=None)

        composite.general_data = self.general_data
        if self.general_data is not None:
            composite.general_data = self.general_data.overlay(below.general_data)

        composite.user_profiles = below.user_profiles
        for user_id in self.user_profiles:
            if user_id not in below.user_profiles:
                composite.user_profiles[user_id] = self.user_profiles[user_id]
            else:
                composite.user_profiles[user_id] = self.user_profiles[user_id].overlay(below.user_profiles[user_id])

        composite.user_followers = below.user_followers
        for user_id in self.user_followers:
            if user_id not in below.user_followers:
                composite.user_followers[user_id] = self.user_followers[user_id]
            else:
                composite.user_followers[user_id] = self.user_followers[user_id].overlay(below.user_followers[user_id])

        composite.projects = below.projects
        for project_id in self.projects:
            if project_id not in below.projects:
                composite.projects[project_id] = self.projects[project_id]
            else:
                composite.projects[project_id] = self.projects[project_id].overlay(below.projects[project_id])

        # Even though data is being pulled from an earlier snapshot, the composite snapshot is still current because
        # the current snapshot overwrites everything that changed.
        composite.start_time = self.start_time
        composite.end_time = self.end_time

        return composite

    def difference(self, below: Self) -> Self:
        if below.is_relative:
            raise ValueError('"below" must be an absolute snapshot')
        if self.is_relative:
            raise ValueError('"difference()" may only be called on absolute snapshots')

        difference = DatabaseSnapshot(last_snapshot=below)

        difference.add_general_data(self.general_data)

        for user_id in self.user_profiles:
            difference.add_user_profile(user_id, self.user_profiles[user_id])
        for user_id in self.user_followers:
            difference.add_user_followers(user_id, self.user_followers[user_id])
        for project_id in self.projects:
            difference.add_project(project_id, self.projects[project_id])

        # The relative snapshot is just as accurate as the newer snapshot, so it uses its timestamps
        difference.start_time = self.start_time
        difference.end_time = self.end_time

        return difference

    def start(self) -> None:
        """
        Sets the start time to the current time and prepares the snapshot for writing.
        Should be called exactly once immediately before fetching data to be archived.

        :rtype: None
        """
        if self.start_time is not None:
            raise RuntimeError('"start()" should only be called once')

        self.start_time = time.time()
        self.end_time = None

    def raise_unless_active(self) -> None:
        """
        Raises a RuntimeError if ``start()`` has not been called, or if ``finish()`` has.

        :rtype: None
        """
        if self.start_time is None:
            raise RuntimeError('"start()" was not called')
        if self.end_time is not None:
            raise RuntimeError('"finish()" was called')

    def finish(self) -> None:
        """
        Sets the end time to the current time and finishes writing.
        Should be called exactly once immediately after all fetched data has been archived.

        :rtype: None
        """
        if self.start_time is None:
            raise RuntimeError('"finish()" should only be called after "start()" has been called')
        if self.end_time is not None:
            raise RuntimeError('"finish()" should only be called once')

        self.end_time = time.time()

        # Remove added IDs that never got metadata attached to them.
        # We do not add these IDs to removed_users or removed_projects because they were not necessarily deleted;
        # rather, they were just unchanged.
        for user_id in list(self.user_profiles.keys()):
            if self.user_profiles[user_id] is None:
                del self.user_profiles[user_id]
        for user_id in list(self.user_followers.keys()):
            if self.user_followers[user_id] is None:
                del self.user_followers[user_id]
        for project_id in list(self.projects.keys()):
            if self.projects[project_id] is None:
                del self.projects[project_id]

    def add_user_id(self, user_id: str) -> None:
        """
        Adds a user ID to the database snapshot.
        If the ID was already in the list, moves it to the end.

        :param user_id: The ID of the user.
        :type user_id: str
        :rtype: None
        """
        self.raise_unless_active()

        if user_id in self.removed_users:
            self.removed_users.remove(user_id)

        if user_id not in self.user_profiles:
            self.user_profiles[user_id] = None
        else:
            self.user_profiles.move_to_end(user_id)

        if user_id not in self.user_followers:
            self.user_followers[user_id] = None
        else:
            self.user_followers.move_to_end(user_id)

    def add_project_id(self, project_id: str) -> None:
        """
        Adds a project ID to the database snapshot.
        If the ID was already in the list, moves it to the end.

        :param project_id: The ID of the project.
        :type project_id: str
        :rtype: None
        """
        self.raise_unless_active()

        if project_id in self.removed_projects:
            self.removed_projects.remove(project_id)

        if project_id not in self.projects:
            self.projects[project_id] = None
        else:
            self.projects.move_to_end(project_id)

    def add_general_data(self, general_data: JSONSnapshot | None) -> None:
        """
        Adds general data to the database snapshot.

        :param general_data: An absolute snapshot of the general data. If None, no changes will occur.
        :type general_data: JSONSnapshot | None
        :rtype: None
        """
        self.raise_unless_active()

        if general_data is None:
            return

        # Validation
        if general_data.is_relative:
            raise ValueError('"general_data" must be an absolute snapshot')

        # Simple case (absolute database snapshot)
        if not self.is_relative:
            self.general_data = general_data
            return

        # Get last data snapshot
        last_data: JSONSnapshot | None = self._last_snapshot.general_data

        # Save the difference between the snapshots
        if last_data is None:
            self.general_data = general_data
            return
        self.general_data = general_data.difference(last_data)

    def add_user_profile(self, user_id: str, user_profile: JSONSnapshot | None) -> None:
        """
        Adds a user profile to the database snapshot.
        Make sure to call ``add_user_id()`` first.

        :param user_id: The ID of the user.
        :type user_id: str
        :param user_profile: An absolute snapshot of the user's profile data. If None, no changes will occur.
        :type user_profile: JSONSnapshot | None
        :rtype: None
        """
        self.raise_unless_active()

        if user_profile is None:
            return

        # Validation
        if user_profile.is_relative:
            raise ValueError('"user_profile" must be an absolute snapshot')
        if user_id not in self.user_profiles:
            raise RuntimeError(f'Cannot add profile to user ID "{user_id}" before their ID is added')

        # Simple case (absolute database snapshot)
        if not self.is_relative:
            self.user_profiles[user_id] = user_profile
            return

        # Get last profile snapshot if it exists
        if user_id not in self._last_snapshot.user_profiles:
            self.user_profiles[user_id] = user_profile
            return
        last_profile: JSONSnapshot | None = self._last_snapshot.user_profiles[user_id]

        # Save the difference between the snapshots
        if last_profile is None:
            self.user_profiles[user_id] = user_profile
            return
        self.user_profiles[user_id] = user_profile.difference(last_profile)

    def add_user_followers(self, user_id: str, user_followers: JSONSnapshot | None) -> None:
        """
        Adds a user's follower list to the database snapshot.
        Make sure to call ``add_user_id()`` first.

        :param user_id: The ID of the user.
        :type user_id: str
        :param user_followers: An absolute snapshot of the user's follower list. If None, no changes will occur.
        :type user_followers: JSONSnapshot | None
        :rtype: None
        """
        self.raise_unless_active()

        if user_followers is None:
            return

        # Validation
        if user_followers.is_relative:
            raise ValueError('"user_followers" must be an absolute snapshot')
        if user_id not in self.user_followers:
            raise RuntimeError(f'Cannot add followers to user ID "{user_id}" before their ID is added')

        # Simple case (absolute database snapshot)
        if not self.is_relative:
            self.user_followers[user_id] = user_followers
            return

        # Get last followers snapshot if it exists
        if user_id not in self._last_snapshot.user_followers:
            self.user_followers[user_id] = user_followers
            return
        last_followers: JSONSnapshot | None = self._last_snapshot.user_followers[user_id]

        # Save the difference between the snapshots
        if last_followers is None:
            self.user_followers[user_id] = user_followers
            return
        self.user_followers[user_id] = user_followers.difference(last_followers)

    def add_project(self, project_id: str, project: JSONSnapshot | None) -> None:
        """
        Adds a project's metadata to the database snapshot.
        Make sure to call ``add_project_id()`` first.

        :param project_id: The ID of the project.
        :type project_id: str
        :param project: An absolute snapshot of the project's metadata. If None, no changes will occur.
        :type project: JSONSnapshot | None
        :rtype: None
        """
        self.raise_unless_active()

        if project is None:
            return

        # Validation
        if project.is_relative:
            raise ValueError('"project" must be an absolute snapshot')
        if project_id not in self.projects:
            raise RuntimeError(f'Cannot add metadata to project ID "{project_id}" before its ID is added')

        # Simple case (absolute database snapshot)
        if not self.is_relative:
            self.projects[project_id] = project
            return

        # Get last metadata snapshot if it exists
        if project_id not in self._last_snapshot.projects:
            self.projects[project_id] = project
            return
        last_metadata: JSONSnapshot | None = self._last_snapshot.projects[project_id]

        # Save the difference between the snapshots
        if last_metadata is None:
            self.projects[project_id] = project
            return
        self.projects[project_id] = project.difference(last_metadata)



if __name__ == '__main__':
    input('Press ENTER to run the test.')

    d = DatabaseSnapshot()
    d.start()
    d.add_general_data(JSONSnapshot({
        'users': 3754,
        'projects': 9237,
        'someotherstuff': 'idk',
    }))
    d.add_user_id('imaginaryuserid')
    d.add_user_profile('imaginaryuserid', JSONSnapshot({
        'username': 'idkman',
        'real_username': 'istilldkman',
        'followers': 23,
        'badges': ['epic', 'sus', 'soupfan'],
        'icant': 'remembertheotherkeys',
    }))
    d.add_user_id('userthatwillbedeleted')
    d.add_user_profile('userthatwillbedeleted', JSONSnapshot({
        'username': 'goodbye',
        'real_username': 'Goodbye',
        'followers': 999,
        'badges': ['soupfan', 'abouttobedeleted'],
    }))
    d.finish()

    d2 = DatabaseSnapshot(last_snapshot=d)
    d2.start()
    d2.add_general_data(JSONSnapshot({
        'users': 3803,
        'projects': 9446,
        'someotherstuff': 'idk',
    }))
    d2.add_user_id('imaginaryuserid')
    d2.add_user_profile('imaginaryuserid', JSONSnapshot({
        'username': 'idkman',
        'real_username': 'istilldkman',
        'followers': 27,
        'privateprofile': False,
        'badges': ['epic', 'sus', 'soupfan', 'eventwinner'],
        'bio': 'i have a bio now ;D',
    }))
    # Don't add "userthatwillbedeleted" so they are deleted
    d2.finish()

    input('Finished! Press ENTER to close the test.')
