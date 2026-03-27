from typing import Any, Optional


class BaseSerializer:
    """
    Framework-agnostic base serializer.

    Purpose:
    - validate input data
    - store field errors
    - expose validated_data only after is_valid() is called
    """

    def __init__(self, data: Any):
        self.initial_data = data
        self._validated_data: Optional[Any] = None
        self._errors: dict[str, Any] = {}

    @property
    def validated_data(self):
        if self._validated_data is None:
            raise ValueError('Call is_valid() before accessing validated_data.')
        return self._validated_data

    @property
    def errors(self) -> dict[str, Any]:
        return self._errors

    def is_valid(self) -> bool:
        self._errors = {}
        self._validated_data = self._validate(self.initial_data)
        return not self._errors

    def _validate(self, data: Any):
        raise NotImplementedError
