"""Domain errors for the alert subsystem."""


class AlertError(Exception):
    """Base class for alert domain errors."""

    status_code: int = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class AlertNotFound(AlertError):
    status_code = 404

    def __init__(self, alert_id: str):
        super().__init__(f"Alert {alert_id} not found")


class InvalidAlertCondition(AlertError):
    status_code = 422

    def __init__(self, message: str = "Invalid alert condition"):
        super().__init__(message)


class InvalidAlertConfiguration(AlertError):
    status_code = 422

    def __init__(self, message: str = "Invalid alert configuration"):
        super().__init__(message)


class AlertExpired(AlertError):
    status_code = 409

    def __init__(self, message: str = "Alert has expired"):
        super().__init__(message)