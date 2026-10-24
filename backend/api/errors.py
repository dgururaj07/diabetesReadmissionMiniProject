class AppError(Exception):
    pass


class NotFoundError(AppError):
    pass


class InvalidInputError(AppError):
    pass
