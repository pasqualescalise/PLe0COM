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
    'decsym': ['--'],
    'eql': ['=='],
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
    'becomes': ['='],
    'comma': [','],
    'constsym': ['const'],
    'varsym': ['var'],
    'procsym': ['procedure'],
    'odd': ['odd'],
    'truesym': ['true'],
    'falsesym': ['false'],
    'not': ['not'],
    'and': ['and'],
    'or': ['or'],
    'print': ['!', 'print'],
    'read': ['?', 'read'],
    'quote': ['"'],
    'panicsym': ['panic']
}


class Lexer:
    """The lexer. Decomposes a string in tokens."""

    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.line_number = 1
        self.str_to_token = list([(s, t) for t, ss in TOKEN_DEFS.items() for s in ss])
        self.str_to_token.sort(key=lambda a: -len(a[0]))

        self.parsed_string = None
        self.skip_quote = False

    def skip_whitespace(self):
        in_comment = False
        inline_comment = False
        while self.pos < len(self.text) and (self.text[self.pos].isspace() or self.text[self.pos:self.pos + 2] == '/*' or self.text[self.pos:self.pos + 2] == '//' or in_comment):
            if self.text[self.pos:self.pos + 2] == '/*' and not in_comment:
                self.pos += 1
                in_comment = True
            elif self.text[self.pos:self.pos + 2] == '*/' and in_comment:
                self.pos += 1
                in_comment = False

            elif self.text[self.pos:self.pos + 2] == '//' and not in_comment:
                self.pos += 1
                in_comment = True
                inline_comment = True
            elif self.text[self.pos] == '\n' and in_comment and inline_comment:
                in_comment = False
                inline_comment = False

            if self.text[self.pos] == '\n':
                self.line_number += 1

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

            # if this string contained newlines, they also count for the total program lines
            self.line_number += 0 if self.parsed_string.count('\n') == 0 else self.parsed_string.count('\n') - 1
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
