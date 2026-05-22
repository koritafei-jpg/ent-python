"""运行时错误。"""


class EntpyError(Exception):
    pass


class ConstraintError(EntpyError):
    pass


class NotFoundError(EntpyError):
    pass


class NotAllowedError(EntpyError):
    pass


class ValidationError(EntpyError):
    pass
