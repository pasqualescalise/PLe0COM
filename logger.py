#!/usr/bin/env python3

"""Logging function using decorators
Usage: decorate monitored function with '@logger'"""


def logger(f):
    def wrapped(*args, **kwargs):
        print('Calling:', f)
        res = f(*args, **kwargs)
        print('Returning from:', f)
        return res

    return wrapped
