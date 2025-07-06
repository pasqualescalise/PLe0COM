#!/usr/bin/env python3

"""Logging functions
Mainly used to add indentations and ANSI formatting"""


def initialize_logger():
    global indentation
    indentation = 0


def logger(f):
    def wrapped(*args, **kwargs):
        global indentation
        function_name = f.__module__.capitalize() + "." + f.__name__ + "()"
        print(f'{" " * indentation * 4}{ANSI("YELLOW", "Calling:")} {function_name}')
        indentation += 1
        res = f(*args, **kwargs)
        indentation -= 1
        print(f'{" " * indentation * 4}{ANSI("BLUE", "Returning from:")} {function_name}')
        return res

    return wrapped


def log_indentation(str):
    str = str.replace("\n", f'\n{" " * indentation * 4}')
    print(f'{" " * indentation * 4}{str}')


BASE = "\033["
RST = BASE + "0m"
CODE = {
    "BLACK": BASE + "30m",
    "RED": BASE + "31m",
    "GREEN": BASE + "32m",
    "YELLOW": BASE + "33m",
    "BLUE": BASE + "34m",
    "MAGENTA": BASE + "35m",
    "CYAN": BASE + "36m",
    "WHITE": BASE + "37m",

    "BOLD": BASE + "01m",
    "ITALIC": BASE + "03m",
    "UNDERLINE": BASE + "04m"
}


def ANSI(code, str):
    if CODE[code] is None:
        return str

    return f"{CODE[code]}{str}{RST}"
    # return f"{str}"


def h1(str):
    return f"\n{CODE['BOLD']}{CODE['ITALIC']}{CODE['UNDERLINE']}{CODE['MAGENTA']}{str}{RST}\n"


def h2(str):
    return f"\n{CODE['BOLD']}{CODE['BLUE']}{str}{RST}\n"


def remove_formatting(str):
    str = str.replace(RST, "")
    for code in CODE.values():
        str = str.replace(code, "")
    return str
