"""Shared test fixtures for mumble-bg."""


class IceOwnedInvalidUserException(Exception):
    """Stand-in for Murmur's ``M.InvalidUserException`` used wherever tests
    simulate Murmur rejecting a register/update because BG's ICE
    authenticator already claims the username.
    """
