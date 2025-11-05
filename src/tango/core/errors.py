"""Module containing custom TANGO errors"""


class TangoError(Exception):
    """Base exception for Tango package"""

    pass


class TangoValueError(TangoError, ValueError):
    """Value validation errors in Tango"""

    pass
