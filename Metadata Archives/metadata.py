from __future__ import annotations

from typing import Any, Union, Self
import time

JSON = Union[dict, list, str, float, bool, None]

class AbstractSingleton:
    """
    Parent type for singleton types.
    """
    _instance: Self | None = None

    def __new__(cls, *args, **kwargs) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

class UnchangedJSONType(AbstractSingleton):
    """
    Type for UnchangedJSON singleton.
    """

UnchangedJSON = UnchangedJSONType()

class DeletedKeyType(AbstractSingleton):
    """
    Type for DeletedKey singleton.
    """

DeletedKey = DeletedKeyType()

def json_difference(new: JSON, old: JSON) -> JSON | UnchangedJSON:
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
        for key in old:
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

def json_reverse_difference(old: JSON, difference: JSON | UnchangedJSON) -> JSON:
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
            value_difference: JSON | UnchangedJSON = difference[i]
            new_value: JSON = json_reverse_difference(old_value, value_difference)
            new.append(new_value)
        return new

    return difference # Cannot take difference for this type; difference is just the new value

class AbstractSnapshot:
    """
    Parent type for snapshots.
    """
    def __init__(self, last_snapshot: Self):
        self._last_snapshot: Self | None = last_snapshot

        # Public attributes are pickled
        self.is_relative: bool = self._last_snapshot is not None

    def __getstate__(self) -> dict[str, Any]:
        attributes: dict[str, Any] = self.__dict__.copy()
        return {i: attributes[i] for i in attributes if not i.startswith('_')}

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)
        # TODO: Set _last_snapshot to contents of last snapshot if self.is_relative is True

class JSONSnapshot(AbstractSnapshot):
    """
    A JSON response from an API.
    May only include changes from the previous snapshot.
    """
    def __init__(self, data: JSON | UnchangedJSONType = UnchangedJSON, failure_message: str | None = None, last_snapshot: JSONSnapshot | None = None):
        super().__init__(last_snapshot)

        # Public attributes are pickled
        self.data: JSON | UnchangedJSONType = UnchangedJSON
        self.failure_message: str | None = failure_message

        # Handle failed snapshots
        if self.failure_message is not None:
            return

        # Handle initial snapshot
        if self._last_snapshot is None:
            self.data = data
            return

class DatabaseSnapshot(AbstractSnapshot):
    """
    The state of the metadata for all users and projects at a given time.
    May only include changes from the previous snapshot.
    """
    def __init__(self, last_snapshot: DatabaseSnapshot | None = None) -> None:
        super().__init__(last_snapshot)

        # Public attributes are pickled
        self.removed_users: frozenset[str] = frozenset()
        self.modified_users: dict[str, UserSnapshot]
        self.modified_projects: dict[str, ProjectSnapshot]
        self.start_time: float | None = None
        self.end_time: float | None = None

    def set_start_time(self) -> None:
        self.start_time = time.time()
        self.end_time = None

    def set_end_time(self) -> None:
        self.end_time = time.time()
