#!/usr/bin/env python3

"""Simple lexer for PL/0 using generators"""

from re import match

# Tokens can have multiple definitions if needed
TOKEN_DEFS = {
    'lparen': ['('],
    'rparen': [')'],
    'lspar': ['['],
    'rspar': [']'],
    'colon': [':'],
    'times': ['*'],
    'slash': ['/'],
    'plus': ['+'],
    'minus': ['-'],
    'shl': ['<<'],
    'shr': ['>>'],
    'mod': ['%'],
    'incsym': ['++'],
    'eql': ['='],
    'neq': ['!='],
    'lss': ['<'],
    'leq': ['<='],
    'gtr': ['>'],
    'geq': ['>='],
    'dontcaresym': ['_'],
    'callsym': ['call'],
    'returns': ['->'],
    'returnsym': ['return'],
    'beginsym': ['begin'],
    'semicolon': [';'],
    'endsym': ['end'],
    'ifsym': ['if'],
    'thensym': ['then'],
    'elifsym': ['elif'],
    'elsesym': ['else'],
    'whilesym': ['while'],
    'forsym': ['for'],
    'dosym': ['do'],
    'becomes': [':='],
    'constsym': ['const'],
    'comma': [','],
    'varsym': ['var'],
    'procsym': ['procedure'],
    'period': ['.'],
    'oddsym': ['odd'],
    'truesym': ['true'],
    'falsesym': ['false'],
    'not': ['not'],
    'and': ['and'],
    'or': ['or'],
    'print': ['!', 'print'],
    'read': ['?', 'read'],
    'quote': ['"']
}


class Lexer:
    """The lexer. Decomposes a string in tokens."""

    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.str_to_token = list([(s, t) for t, ss in TOKEN_DEFS.items() for s in ss])
        self.str_to_token.sort(key=lambda a: -len(a[0]))

        self.parsed_string = None
        self.skip_quote = False

    def skip_whitespace(self):
        in_comment = False
        while self.pos < len(self.text) and (self.text[self.pos].isspace() or self.text[self.pos] == '{' or in_comment):
            if self.text[self.pos] == '{' and not in_comment:
                in_comment = True
            elif in_comment and self.text[self.pos] == '}':
                in_comment = False
            self.pos += 1

    def check_symbol(self):
        for s, t in self.str_to_token:
            if self.text[self.pos:self.pos + len(s)].lower() == s:
                # allow stuff like "varname" as an ident: "var" is alphanumeric, "n" is alphanumeric, so
                # don't parse "var" as a token; same applies for stuff like var_name
                if s.isalnum() and (self.text[self.pos + len(s)].isalnum() or self.text[self.pos + len(s)] == "_"):
                    continue
                self.pos += len(s)
                return t, s
        return None, None

    def get_valid_string(self):
        if self.parsed_string is not None:
            self.parsed_string = None
            return True

        regex_match = match(r'\"(?:[^\"\\{]|\\.)*\"', '"' + self.text[self.pos:])
        if regex_match:
            found = regex_match.group(0)
            self.parsed_string = found[1:-1]
            return True

        return False

    def check_regex(self, regex):
        regex_match = match(regex, self.text[self.pos:])
        if not regex_match:
            return None
        found = regex_match.group(0)
        self.pos += len(found)
        return found

    def tokens(self):
        """Returns a generator which will produce a stream of (token identifier, token value) pairs."""

        while self.pos < len(self.text):
            if self.parsed_string is None:
                self.skip_whitespace()
            else:  # return the parsed string
                self.pos += len(self.parsed_string)
                yield 'string', self.parsed_string
                self.skip_quote = True
                self.parsed_string = None
                continue
            t, s = self.check_symbol()
            if s:
                if t == 'quote' and not self.skip_quote:
                    if self.parsed_string == "":
                        self.pos -= 1
                        self.parsed_string = None
                        self.skip_quote = True
                        yield 'string', ""
                        continue

                    if not self.get_valid_string():
                        break
                self.skip_quote = False
                yield t, s
                continue
            t = self.check_regex(r'[0-9]+')
            if t:
                yield 'number', int(t)
                continue
            t = self.check_regex(r'\w+')
            if t:
                yield 'ident', t
                continue
            try:
                t = self.text[self.pos]
            except Exception:
                yield 'end of file', 'EOF'
                break
            yield 'illegal', t
            break

        yield 'illegal', None
