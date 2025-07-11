#!/usr/bin/env python3

"""Intermediate Representation
Could be improved by relying less on class hierarchy and more on string tags
and/or duck typing. Includes lowering and flattening functions. Every node must
have a lowering function or a code generation function (codegen functions are
in a separate module though)."""

from functools import reduce
from copy import deepcopy

from codegenhelp import REGISTER_SIZE
from logger import log_indentation, ii, li, red, green, yellow, blue, magenta, cyan, bold, italic, underline
import logger

# UTILITIES

temporary_count = 0
data_variables_count = 0


def new_temporary(symtab, type):
    global temporary_count
    temp = Symbol(name=f"t{temporary_count}", stype=type, alloct='reg')
    temporary_count += 1
    return temp


def new_variable_name():
    global data_variables_count
    name = f"data{data_variables_count}"
    data_variables_count += 1
    return name


# TYPES

# NOTE: the type system is very simple, so that we don't need explicit cast
# instructions or too much handling in the codegen phase.
# Basically, the type system always behaves as every term of an expression was
# casted to the biggest type available, and the result is then casted to the
# biggest of the types of the terms.
# Also, no handling for primitive types that do not fit in a single machine
# register is provided.


BASE_TYPES = ['Int', 'Label', 'Struct', 'Function']
TYPE_QUALIFIERS = ['unsigned']


class Type:
    def __init__(self, name, size, basetype, qualifiers=None):
        if qualifiers is None:
            qualifiers = []
        self.size = size
        self.basetype = basetype
        self.qual_list = qualifiers
        self.name = name if name else self.default_name()

    def default_name(self):
        n = ''
        if 'unsigned' in self.qual_list:
            n += 'u'
        n += 'int'  # no float types exist at the moment
        return n


class ArrayType(Type):
    def __init__(self, name, dims, basetype):
        """dims is a list of dimensions: dims = [5]: array of 5 elements;
        dims = [5, 5]: 5x5 matrix; and so on"""
        self.dims = dims
        if basetype is not None:
            super().__init__(name, reduce(lambda a, b: a * b, dims) * basetype.size, basetype)
            self.name = name if name else self.default_name()

    def default_name(self):
        return self.basetype.name + repr(self.dims)


class StructType(Type):  # currently unused
    def __init__(self, name, size, fields):
        self.fields = fields
        realsize = sum([f.size for f in self.fields])
        super().__init__(name, realsize, 'Struct', [])

    def get_size(self):
        return sum([f.size for f in self.fields])


class LabelType(Type):
    def __init__(self):
        super().__init__('label', 0, 'Label', [])
        self.ids = 0

    def __call__(self, target=None):
        self.ids += 1
        return Symbol(name=f"label{self.ids}", stype=self, value=target)


class FunctionType(Type):
    def __init__(self):
        super().__init__('function', 0, 'Function', [])


class PointerType(Type):  # can't define a variable as type PointerType, it's used for arrays
    def __init__(self, ptrto):
        """ptrto is the type of the object that this pointer points to."""
        super().__init__('&' + ptrto.name, REGISTER_SIZE, 'Int', ['unsigned'])
        self.pointstotype = ptrto


TYPENAMES = {
    'int': Type('int', 32, 'Int'),
    'short': Type('short', 16, 'Int'),
    'byte': Type('byte', 8, 'Int'),

    'uint': Type('uint', 32, 'Int', ['unsigned']),
    'ushort': Type('ushort', 16, 'Int', ['unsigned']),
    'ubyte': Type('ubyte', 8, 'Int', ['unsigned']),

    'char': Type('char', 8, 'Char', ['unsigned']),

    'label': LabelType(),
    'function': FunctionType(),
}

ALLOC_CLASSES = ['global', 'auto', 'data', 'reg', 'imm', 'param', 'return']


class Symbol:
    """There are 7 classes of allocation for symbols:\n
    - allocation to a register ('reg')
    - allocation to an arbitrary memory location, in the current stack frame
      ('auto') or in the .comm section ('global')
    - allocation in the data section ('data')
    - allocation to an immediate ('imm')
    - allocation of function parameters('param')
    - allocation of function retuns('return') -> these are not 'real' symbols
      because they can't be referenced, but are needed to know where on the stack
      to put return values"""

    def __init__(self, name, stype, value=None, alloct='auto', fname='', used_in_nested_procedure=False):
        self.name = name
        self.stype = stype
        self.value = value  # if not None, it is a constant
        self.alloct = alloct
        self.allocinfo = None
        # useful to understand the scope of the symbol
        self.fname = fname
        # if a variable is used in a nested procedure in cannot be promoted to a register
        self.used_in_nested_procedure = used_in_nested_procedure

    def set_alloc_info(self, allocinfo):
        self.allocinfo = allocinfo  # in byte

    def is_string(self):
        """A Symbol references a string if it's of type char[] or &char"""
        return isinstance(self.stype, ArrayType) and self.stype.basetype.name == "char" or isinstance(self.stype, PointerType) and self.stype.pointstotype.name == "char"

    def __repr__(self):
        base = f"{self.alloct} {self.stype.name}"

        if type(self.stype) == FunctionType or type(self.stype) == LabelType:
            base = f"{base} {magenta(f'{self.name}')}"
        elif self.alloct != "reg":
            base = f"{base} {green(f'{self.name}')}"
        else:
            base = f"{base} {red(f'{self.name}')}"
        if self.allocinfo is not None:
            base = f"{base} {{{yellow(italic(f'{self.allocinfo}'))}}}"
        return base


class SymbolTable(list):
    def find(self, node, name):
        log_indentation(underline(f"Looking up {name}"))
        for s in self:
            if s.alloct == "param":
                # for parameters it's not enough to check the name, also
                # the called function must be the one being parsed to
                # make sure to get the correct variable in the scope
                try:
                    if s.fname == node.current_function and s.name == name:
                        return s
                except AttributeError:
                    pass  # trying to use find outside of the parser
            elif s.name == name:
                try:
                    if s.fname != node.current_function:
                        s.used_in_nested_procedure = True
                except AttributeError:
                    pass  # trying to use find outside of the parser
                return s
        raise RuntimeError(f"Looking up for symbol {name} in function {node.current_function} failed!")

    def __repr__(self):
        res = f"{cyan('SymbolTable')} " + '{\n'
        for symbol in self:
            res += f"\t{symbol}\n"
        res += "}"
        return res

    def exclude(self, barred_types):
        return [symb for symb in self if symb.stype not in barred_types]


class DataSymbolTable():
    data_symtab = SymbolTable()

    @staticmethod
    def add_data_symbol(symbol):
        DataSymbolTable.data_symtab.append(symbol)

    @staticmethod
    def get_data_symtab():
        return DataSymbolTable.data_symtab


# IRNODE

class IRNode:  # abstract
    def __init__(self, parent=None, children=None, symtab=None):
        self.symtab = symtab
        self.parent = parent
        if children:
            self.children = children[:]
            for c in self.children:
                try:
                    c.parent = self
                except Exception:
                    # TODO: error checking
                    pass
        else:
            self.children = []

    def __repr__(self):
        try:
            # TODO: print this better (a non-empty statement with a label)
            label = f"{magenta(f'{self.get_label().name}')}: "
        except Exception:
            label = ''

        try:
            hre = self.human_repr()
            return f"{label}{hre}"
        except Exception:
            pass

        attrs = {'body', 'cond', 'value', 'thenpart', 'elifspart', 'elsepart', 'symbol', 'call', 'init', 'step', 'expr', 'target', 'defs', 'global_symtab', 'local_symtab', 'offset', 'function_symbol'} & set(dir(self))

        res = f"{cyan(f'{self.type()}')}, {id(self)}" + " {"
        if self.parent is not None:
            # res += f"\nparent: {id(self.parent)};\n"
            res += "\n"
            pass
        else:
            # a missing parent is not a bug only for the root node, but at this
            # level of abstraction there is no way to distinguish between the root
            # node and a node with a missing parent
            res += red(" MISSING PARENT\n")

        res = f"{label}{res}"

        if "children" in dir(self) and len(self.children):
            res += ii("children: {\n")
            for child in self.children:
                if isinstance(child, EmptyStat):
                    res += li(f"{child}\n")  # label
                else:
                    rep = repr(child).split("\n")
                    res += "\n".join([f"{' ' * 8}" + s for s in rep])
                    res += "\n"
            res += ii("}\n")

        for attr in attrs:
            node = getattr(self, attr)
            rep = repr(node).split("\n")
            if len(rep) > 1:
                reps = "\n".join([f"{' ' * 8}" + s for s in rep[1:]])
                rep = f"{rep[0]}\n{reps}"
            else:
                rep = f"{rep[0]}"
            res += ii(f"{cyan(f'{attr}')} {bold('->')} {rep}\n")

        res += "}"
        return res

    def type(self):
        return str(type(self)).split("'")[1]

    def navigate(self, action, *args, quiet=False):
        attrs = {'body', 'cond', 'value', 'thenpart', 'elifspart', 'elsepart', 'symbol', 'call', 'init', 'step', 'expr', 'target', 'defs', 'global_symtab', 'local_symtab', 'offset'} & set(dir(self))

        if 'children' in dir(self) and len(self.children):
            if not quiet:
                log_indentation(f"Navigating to {cyan(len(self.children))} children of {cyan(self.type())}, {id(self)}")
            for node in self.children:
                try:
                    logger.indentation += 1
                    node.navigate(action, *args, quiet=quiet)
                    logger.indentation -= 1
                except AttributeError:
                    logger.indentation -= 1

        for attr in attrs:
            try:
                if not quiet:
                    log_indentation(f"Navigating to attribute {cyan(attr)} of {cyan(self.type())}, {id(self)}")
                logger.indentation += 1
                node = getattr(self, attr)
                node.navigate(action, *args, quiet=quiet)
                logger.indentation -= 1
            except AttributeError:
                logger.indentation -= 1
        if not quiet:
            log_indentation(f"Navigating to {cyan(self.type())}, {id(self)}")

        # XXX: shitty solution
        try:
            action(self, *args)
        except TypeError:
            action(self)

    def replace(self, old, new):
        new.parent = self
        if 'children' in dir(self) and len(self.children) and old in self.children:
            self.children[self.children.index(old)] = new
            return True
        attrs = {'body', 'cond', 'value', 'thenpart', 'elifspart', 'elsepart', 'symbol', 'call', 'init', 'step', 'expr', 'target', 'defs', 'global_symtab', 'local_symtab', 'offset'} & set(dir(self))

        for d in attrs:
            try:
                if getattr(self, d) == old:
                    setattr(self, d, new)
                    return True
            except AttributeError:
                pass
        return False

    # fix mistakes introduced by deepcoping node:
    #   + assign the correct parents
    #   + switch the new Symbols with the old ones, so all the symbols correspond to the correct object
    def deepcopy_fix(self, symtab):
        attrs = {'body', 'cond', 'value', 'thenpart', 'elifspart', 'elsepart', 'symbol', 'call', 'init', 'step', 'expr', 'target', 'defs',
                 'global_symtab', 'local_symtab', 'offset'} & set(dir(self))
        if 'children' in dir(self) and len(self.children):
            for node in self.children:
                try:
                    node.parent = self

                    if type(node) is Symbol:
                        real_symbol = symtab.find(None, node.name)
                        self.replace(node, real_symbol)

                    node.deepcopy_fix(symtab=symtab)
                except AttributeError:
                    pass
        for d in attrs:
            try:
                getattr(self, d).parent = self

                if type(getattr(self, d)) is Symbol:
                    real_symbol = symtab.find(None, getattr(self, d).name)
                    self.replace(getattr(self, d), real_symbol)

                getattr(self, d).deepcopy_fix(symtab=symtab)
            except AttributeError:
                pass

    def get_function(self):
        if not self.parent:
            return 'global'
        elif type(self.parent) == FunctionDef:
            return self.parent
        else:
            return self.parent.get_function()

    def find_the_program(self):
        if self.parent:
            return self.parent.find_the_program()
        else:
            return self

    # returns the FuncDef with the symbol specified, if it's reachable
    # raises a RuntimeError if it doesn't find it
    def get_function_definition(self, function_symbol):
        function_definition = self.get_function()

        # it's the main function
        if function_definition == 'global':
            program = self.find_the_program()
            for definition in program.defs.children:
                if type(definition) == FunctionDef and definition.symbol == function_symbol:
                    return definition

            if function_definition == 'global':
                raise RuntimeError('Can\'t find function ' + str(function_symbol))

        # it's the current function
        if function_definition.symbol == function_symbol:
            return function_definition

        # it's one of the functions defined in the current function
        for definition in function_definition.body.defs.children:
            if type(definition) == FunctionDef and definition.symbol == function_symbol:
                return definition

        # it's a function defined in the parent
        return function_definition.get_function_definition(function_symbol)

    def get_label(self):
        raise NotImplementedError

    def human_repr(self):
        raise NotImplementedError


# CONST and VAR

class Const(IRNode):
    def __init__(self, parent=None, value=0, symb=None, symtab=None):
        log_indentation(bold(f"New Const Node (id: {id(self)})"))
        super().__init__(parent, None, symtab)
        self.value = value
        self.symbol = symb

    def lower(self):
        if self.symbol is None:
            new = new_temporary(self.symtab, TYPENAMES['int'])
            loadst = LoadImmStat(dest=new, val=self.value, symtab=self.symtab)
        else:
            new = new_temporary(self.symtab, self.symbol.stype)
            loadst = LoadStat(dest=new, symbol=self.symbol, symtab=self.symtab)
        return self.parent.replace(self, StatList(children=[loadst], symtab=self.symtab))


class Var(IRNode):
    """loads in a temporary the value pointed to by the symbol"""

    def __init__(self, parent=None, var=None, symtab=None):
        log_indentation(bold(f"New Var Node (id: {id(self)})"))
        super().__init__(parent, None, symtab)
        self.symbol = var

    def used_variables(self):
        return [self.symbol]

    def lower(self):
        """Var translates to a load statement to the same temporary that is used in
        a following stage for doing the computations (destination())"""
        new = new_temporary(self.symtab, self.symbol.stype)
        loadst = LoadStat(dest=new, symbol=self.symbol, symtab=self.symtab)
        return self.parent.replace(self, StatList(children=[loadst], symtab=self.symtab))


class ArrayElement(IRNode):
    """loads in a temporary the value pointed by: the symbol + the index"""

    def __init__(self, parent=None, var=None, offset=None, symtab=None):
        """offset can NOT be a list of exps in case of multi-d arrays; it should
        have already been flattened beforehand"""
        log_indentation(bold(f"New ArrayElement Node (id: {id(self)})"))
        super().__init__(parent, [offset], symtab)
        self.symbol = var
        self.offset = offset

    def used_variables(self):
        a = [self.symbol]
        a += self.offset.used_variables()
        return a

    def lower(self):
        global TYPENAMES
        dest = new_temporary(self.symtab, self.symbol.stype.basetype)
        off = self.offset.destination()

        statl = [self.offset]

        ptrreg = new_temporary(self.symtab, PointerType(self.symbol.stype.basetype))
        loadptr = LoadPtrToSym(dest=ptrreg, symbol=self.symbol, symtab=self.symtab)
        src = new_temporary(self.symtab, PointerType(self.symbol.stype.basetype))
        add = BinStat(dest=src, op='plus', srca=ptrreg, srcb=off, symtab=self.symtab)
        statl += [loadptr, add]

        statl += [LoadStat(dest=dest, symbol=src, symtab=self.symtab)]
        return self.parent.replace(self, StatList(children=statl, symtab=self.symtab))


class String(IRNode):
    """Puts a fixed string in the data SymbolTable"""

    def __init__(self, parent=None, value="", symtab=None):
        log_indentation(bold(f"New String Node (id: {id(self)})"))
        super().__init__(parent, None, symtab)
        self.value = value

    def used_variables(self):
        return []

    def lower(self):
        # put the string in the data SymbolTable TODO: should it be char[] or just char?
        data_variable = Symbol(name=new_variable_name(), stype=TYPENAMES['char'], value=self.value, alloct='data')
        DataSymbolTable.add_data_symbol(data_variable)

        # load the fixed data string address
        ptrreg_data = new_temporary(self.symtab, PointerType(data_variable.stype))
        access_string = LoadPtrToSym(dest=ptrreg_data, symbol=data_variable, symtab=self.symtab)

        return self.parent.replace(self, StatList(children=[access_string], symtab=self.symtab))


# EXPRESSIONS

class Expr(IRNode):  # abstract
    def get_operator(self):
        return self.children[0]

    def used_variables(self):
        uses = []
        for c in self.children:
            try:
                uses += c.used_variables()
            except AttributeError:
                pass
        return uses


class BinExpr(Expr):
    def __init__(self, parent=None, children=None, symtab=None):
        log_indentation(bold(f"New BinExpr Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)

    def get_operands(self):
        return self.children[1:]

    def lower(self):
        srca = self.children[1].destination()
        srcb = self.children[2].destination()

        # Type promotion.
        if ('unsigned' in srca.stype.qual_list) and ('unsigned' in srcb.stype.qual_list):
            desttype = Type(None, max(srca.stype.size, srcb.stype.size), 'Int', ['unsigned'])
        else:
            desttype = Type(None, max(srca.stype.size, srcb.stype.size), 'Int')

        dest = new_temporary(self.symtab, desttype)

        if self.children[0] != "slash":
            stmt = BinStat(dest=dest, op=self.children[0], srca=srca, srcb=srcb, symtab=self.symtab)
            statl = [self.children[1], self.children[2], stmt]
            return self.parent.replace(self, StatList(children=statl, symtab=self.symtab))

        """
        implement the division as a while loop
        so that `res = op1 / op2`
        becomes something like

        res = 0;
        while (op2 >= 0) {
            op2 = op2 - op1;
            res++;
        }
        """
        zero_destination = LoadImmStat(dest=dest, val=0, symtab=self.symtab)

        one = new_temporary(self.symtab, TYPENAMES['int'])
        load_one = LoadImmStat(dest=one, val=1, symtab=self.symtab)

        entry_label = TYPENAMES['label']()
        entry_stat = EmptyStat(self.parent, symtab=self.symtab)
        entry_stat.set_label(entry_label)

        exit_label = TYPENAMES['label']()
        exit_stat = EmptyStat(self.parent, symtab=self.symtab)
        exit_stat.set_label(exit_label)

        condition_variable = new_temporary(self.symtab, TYPENAMES['int'])
        loop_condition = BinStat(dest=condition_variable, op="geq", srca=srca, srcb=srcb, symtab=self.symtab)

        test_condition = BranchStat(cond=condition_variable, target=exit_label, negcond=True, symtab=self.symtab)

        loop_update = BinStat(dest=srca, op="minus", srca=srca, srcb=srcb, symtab=self.symtab)

        calc_result = BinStat(dest=dest, op="plus", srca=dest, srcb=one, symtab=self.symtab)

        loop_resume = BranchStat(target=entry_label, symtab=self.symtab)

        statl = [self.children[1], self.children[2], zero_destination, load_one, entry_stat, loop_condition, test_condition, loop_update, calc_result, loop_resume, exit_stat]
        return self.parent.replace(self, StatList(children=statl, symtab=self.symtab))


class UnExpr(Expr):
    def __init__(self, parent=None, children=None, symtab=None):
        log_indentation(bold(f"New UnExpr Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)

    def get_operand(self):
        return self.children[1]

    def lower(self):
        src = self.children[1].destination()
        dest = new_temporary(self.symtab, src.stype)
        stmt = UnaryStat(dest=dest, op=self.children[0], src=src, symtab=self.symtab)
        statl = [self.children[1], stmt]
        return self.parent.replace(self, StatList(children=statl, symtab=self.symtab))


class CallExpr(Expr):
    def __init__(self, parent=None, function_symbol=None, parameters=[], symtab=None):
        log_indentation(bold(f"New CallExpr Node (id: {id(self)})"))
        super().__init__(parent, parameters, symtab)
        self.function_symbol = function_symbol

    # raises RuntimeError if the number of parameters or of returns is wrong
    # TODO: add type checking
    def check_parameters_and_returns(self):
        # check that the number of parameters is correct
        if len(self.children) != len(self.function_definition.parameters):
            raise RuntimeError('Not specified the right amount of parameters')

        # check that the call asks for exactly as many values as the function returns (including dont'cares)
        if len(self.function_definition.returns) != len(self.parent.returns):
            raise RuntimeError('Too few or too many values are being returned')

    def lower(self):
        self.function_definition = self.get_function_definition(self.function_symbol)
        self.check_parameters_and_returns()

        stats = self.children[:]

        # save space for eventual return variables
        if len(self.parent.returns) > 0:
            space_needed = 0
            for i in range(len(self.parent.returns)):
                if self.parent.returns[i] == "_":
                    space_needed -= self.function_definition.returns[i].stype.size // 8
                else:
                    space_needed -= self.parent.returns[i].stype.size // 8
            stats.append(SaveSpaceStat(space_needed=space_needed, symtab=self.symtab))

        function_definition_symbols = []
        for symbol in self.function_definition.parameters:
            if symbol.alloct == 'param':
                function_definition_symbols.append(symbol)

        # put the parameters on the stack
        for i in range(len(self.children)):
            stats += [StoreStat(symbol=self.children[i].destination(), dest=function_definition_symbols[i], symtab=self.symtab)]

        return self.parent.replace(self, StatList(children=stats, symtab=self.symtab))


# STATEMENTS

class Stat(IRNode):  # abstract
    def __init__(self, parent=None, children=None, symtab=None):
        super().__init__(parent, children, symtab)
        self.label = None

    def set_label(self, label):
        self.label = label
        label.value = self  # set target

    def get_label(self):
        return self.label

    def used_variables(self):
        return []

    def killed_variables(self):
        return []


class SaveSpaceStat(Stat):  # low-level node
    """ Save space for eventual return statements by pushing null values
        Just needed a statement that would survive until codegen and would
        not matter for datalayout"""

    def __init__(self, parent=None, space_needed=0, symtab=None):
        log_indentation(bold(f"New SaveSpaceStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.space_needed = space_needed

    def used_variables(self):
        return []

    def human_repr(self):
        if self.space_needed < 0:
            return 'save space for the return values'
        else:
            return 'remove useless return values'


class CallStat(Stat):
    """Procedure call"""

    def __init__(self, parent=None, call_expr=None, function_symbol=None, returns=[], symtab=None):
        log_indentation(bold(f"New CallStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.call = call_expr
        self.call.parent = self
        self.function_symbol = function_symbol
        self.returns = returns
        for ret in self.returns:
            if ret != "_":
                ret.parent = self

    def used_variables(self):
        return self.call.used_variables() + self.symtab.exclude([TYPENAMES['function'], TYPENAMES['label']])

    def lower(self):
        self.function_definition = self.get_function_definition(self.function_symbol)

        space_needed_for_parameters = 0
        for param in self.function_definition.parameters:
            space_needed_for_parameters += param.stype.size // 8

        branch = BranchStat(target=self.function_symbol, symtab=self.symtab, is_call=True, space_needed_for_parameters=space_needed_for_parameters)

        stats = [self.call, branch]

        # load the returned values in the correct symbols
        # first load the returned value in a temporary, then store its value in memory
        # this must be done here because it happens after the branch
        for i in range(len(self.returns)):
            if self.returns[i] != "_":
                temp = new_temporary(self.symtab, self.function_definition.returns[i].stype)
                stats += [LoadStat(symbol=self.function_definition.returns[i], dest=temp, symtab=self.symtab)]
                stats += [StoreStat(symbol=temp, dest=self.returns[i], symtab=self.symtab)]
            else:
                space_needed = self.function_definition.returns[i].stype.size // 8
                stats += [SaveSpaceStat(space_needed=space_needed, symtab=self.symtab)]

        return self.parent.replace(self, StatList(children=stats, symtab=self.symtab))


class IfStat(Stat):
    def __init__(self, parent=None, cond=None, thenpart=None, elifspart=None, elsepart=None, symtab=None):
        log_indentation(bold(f"New IfStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.cond = cond
        self.thenpart = thenpart
        self.elifspart = elifspart
        self.elsepart = elsepart
        self.cond.parent = self
        self.thenpart.parent = self

        if self.elifspart:
            self.elifspart.parent = self

        if self.elsepart:
            self.elsepart.parent = self

    def lower(self):
        exit_label = TYPENAMES['label']()
        exit_stat = EmptyStat(self.parent, symtab=self.symtab)
        exit_stat.set_label(exit_label)

        # no elifs and no else
        if not self.elifspart and not self.elsepart:
            branch_to_exit = BranchStat(cond=self.cond.destination(), target=exit_label, symtab=self.symtab)
            stat_list = StatList(self.parent, [self.cond, branch_to_exit, self.thenpart, exit_stat], self.symtab)
            return self.parent.replace(self, stat_list)

        then_label = TYPENAMES['label']()
        self.thenpart.set_label(then_label)
        branch_to_then = BranchStat(cond=self.cond.destination(), target=then_label, symtab=self.symtab)
        branch_to_exit = BranchStat(target=exit_label, symtab=self.symtab)

        stats = [self.cond, branch_to_then]

        # elifs branches
        for i in range(0, len(self.elifspart.children), 2):
            elif_label = TYPENAMES['label']()
            self.elifspart.children[i + 1].set_label(elif_label)
            branch_to_elif = BranchStat(cond=self.elifspart.children[i].destination(), target=elif_label, symtab=self.symtab)
            stats = stats[:] + [self.elifspart.children[i], branch_to_elif]

        # else
        if self.elsepart:
            stats = stats[:] + [self.elsepart, branch_to_exit]

        stats.append(self.thenpart)

        # elifs statements
        for i in range(0, len(self.elifspart.children), 2):
            stats = stats[:] + [branch_to_exit, self.elifspart.children[i + 1]]

        stats.append(exit_stat)
        stat_list = StatList(self.parent, stats, self.symtab)
        return self.parent.replace(self, stat_list)


class WhileStat(Stat):
    def __init__(self, parent=None, cond=None, body=None, symtab=None):
        log_indentation(bold(f"New WhileStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.cond = cond
        self.body = body
        self.cond.parent = self
        self.body.parent = self

    def lower(self):
        entry_label = TYPENAMES['label']()
        exit_label = TYPENAMES['label']()
        exit_stat = EmptyStat(self.parent, symtab=self.symtab)
        exit_stat.set_label(exit_label)
        self.cond.set_label(entry_label)
        branch = BranchStat(cond=self.cond.destination(), target=exit_label, negcond=True, symtab=self.symtab)
        loop = BranchStat(target=entry_label, symtab=self.symtab)
        stat_list = StatList(self.parent, [self.cond, branch, self.body, loop, exit_stat], self.symtab)
        return self.parent.replace(self, stat_list)


class ForStat(Stat):
    def __init__(self, parent=None, init=None, cond=None, step=None, body=None, symtab=None):
        log_indentation(bold(f"New ForStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.init = init
        self.cond = cond
        self.step = step
        self.body = body
        self.init.parent = self
        self.cond.parent = self
        self.step.parent = self
        self.body.parent = self

    def lower(self):
        entry_label = TYPENAMES['label']()
        exit_label = TYPENAMES['label']()
        exit_stat = EmptyStat(self.parent, symtab=self.symtab)
        exit_stat.set_label(exit_label)
        self.cond.set_label(entry_label)
        branch = BranchStat(cond=self.cond.destination(), target=exit_label, negcond=True, symtab=self.symtab)
        loop = BranchStat(target=entry_label, symtab=self.symtab)
        stat_list = StatList(self.parent, [self.init, self.cond, branch, self.body, self.step, loop, exit_stat], self.symtab)
        return self.parent.replace(self, stat_list)

    def unroll(self, unrolling_factor):
        return
        original_body = self.body.children[:]

        loop_end = self.cond.children[-1]
        factor = Const(value=unrolling_factor, symtab=self.symtab)

        # modulus = BinExpr(parent=self, children=['mod', loop_end, factor], symtab=self.symtab)
        modulus = BinExpr(parent=self, children=['shr', loop_end, factor], symtab=self.symtab)
        self.cond.children[-1] = modulus

        copy_step = deepcopy(self.step)
        copy_step.deepcopy_fix(symtab=self.symtab)

        for i in range(unrolling_factor - 1):
            self.body.append(copy_step)

            for child in original_body:
                copy_child = deepcopy(child)
                copy_child.deepcopy_fix(symtab=self.symtab)
                self.body.append(copy_child)

        # cleanup
        # TODO: append it to the parent of the ForStat right after it
        # loop_end = self.cond.children[-1]
        # if unrolling_factor == 2:
        #     pass
        # else:
        #     pass


class AssignStat(Stat):
    def __init__(self, parent=None, target=None, offset=None, expr=None, symtab=None):
        log_indentation(bold(f"New AssignStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.symbol = target

        # TODO: why do this?
        try:
            self.symbol.parent = self
        except AttributeError:
            pass

        self.expr = expr
        if self.expr is not None:
            self.expr.parent = self

        self.offset = offset
        if self.offset is not None:
            self.offset.parent = self

    def used_variables(self):
        try:
            a = self.symbol.used_variables()
        except AttributeError:
            a = []

        try:
            a += self.offset.used_variables()
        except AttributeError:
            pass

        try:
            return a + self.expr.used_variables()
        except AttributeError:
            return a

    def killed_variables(self):
        return [self.symbol]

    def lower(self):
        """Assign statements translate to a store stmt, with the symbol and a
        temporary as parameters."""
        src = self.expr.destination()
        dst = self.symbol

        stats = [self.expr]

        if not dst.is_string():
            if self.offset:
                off = self.offset.destination()
                desttype = dst.stype
                if type(desttype) is ArrayType:  # this is always true at the moment
                    desttype = desttype.basetype
                ptrreg = new_temporary(self.symtab, PointerType(desttype))
                loadptr = LoadPtrToSym(dest=ptrreg, symbol=dst, symtab=self.symtab)
                dst = new_temporary(self.symtab, PointerType(desttype))
                add = BinStat(dest=dst, op='plus', srca=ptrreg, srcb=off, symtab=self.symtab)
                stats += [self.offset, loadptr, add]

            stats += [StoreStat(dest=dst, symbol=src, symtab=self.symtab)]

            return self.parent.replace(self, StatList(children=stats, symtab=self.symtab))

        """
        Assign a variable to a fixed string by getting a fixed string from the data section, then
        copying one by one its characters from the fixed string to the variable one
        """
        ptrreg_data = src

        # load the variable data string address
        ptrreg_var = new_temporary(self.symtab, PointerType(self.symbol.stype.basetype))
        access_var = LoadPtrToSym(dest=ptrreg_var, symbol=self.symbol, symtab=self.symtab)

        counter = new_temporary(self.symtab, TYPENAMES['int'])
        counter_initialize = LoadImmStat(dest=counter, val=0, symtab=self.symtab)

        zero = new_temporary(self.symtab, TYPENAMES['int'])
        zero_initialize = LoadImmStat(dest=zero, val=0, symtab=self.symtab)

        one = new_temporary(self.symtab, TYPENAMES['int'])
        one_initialize = LoadImmStat(dest=one, val=1, symtab=self.symtab)

        # load first char of data
        character = new_temporary(self.symtab, TYPENAMES['char'])
        load_data_char = LoadStat(dest=character, symbol=ptrreg_data, symtab=self.symtab)

        # while the char loaded from the fixed string is different from 0x0,
        # copy the chars from the fixed string to the variable one
        dest = new_temporary(self.symtab, TYPENAMES['int'])
        cond = BinStat(dest=dest, op='neq', srca=character, srcb=zero, symtab=self.symtab)

        load_data_char = LoadStat(dest=character, symbol=ptrreg_data, symtab=self.symtab)

        store_var_char = StoreStat(dest=ptrreg_var, symbol=character, symtab=self.symtab)

        increment_data = BinStat(dest=ptrreg_data, op='plus', srca=ptrreg_data, srcb=one, symtab=self.symtab)
        increment_var = BinStat(dest=ptrreg_var, op='plus', srca=ptrreg_var, srcb=one, symtab=self.symtab)
        increment_counter = BinStat(dest=counter, op='plus', srca=counter, srcb=one, symtab=self.symtab)

        body_stats = [load_data_char, store_var_char, increment_data, increment_var, increment_counter]

        body = StatList(children=body_stats, symtab=self.symtab)
        while_loop = WhileStat(cond=cond, body=body, symtab=self.symtab)

        # put a terminator 0x0 byte in the variable string
        end_zero_string = StoreStat(dest=ptrreg_var, symbol=zero, symtab=self.symtab)

        stats += [access_var, counter_initialize, zero_initialize, one_initialize, load_data_char, while_loop, end_zero_string]
        statl = StatList(children=stats, symtab=self.symtab)

        # XXX: little trick to lower while statement here
        while_loop.parent = statl
        while_loop.lower()

        return self.parent.replace(self, statl)


class PrintStat(Stat):
    def __init__(self, parent=None, expr=None, symtab=None):
        log_indentation(bold(f"New PrintStat Node (id: {id(self)})"))
        super().__init__(parent, [expr], symtab)
        self.expr = expr

    def used_variables(self):
        return self.expr.used_variables()

    def lower(self):
        print_string = False

        if self.expr and self.expr.destination().is_string():
            print_string = True

        pc = PrintCommand(src=self.expr.destination(), print_string=print_string, symtab=self.symtab)
        stlist = StatList(children=[self.expr, pc], symtab=self.symtab)
        return self.parent.replace(self, stlist)


class PrintCommand(Stat):  # low-level node
    def __init__(self, parent=None, src=None, print_string=False, symtab=None):
        log_indentation(bold(f"New PrintCommand Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.src = src
        if src.alloct != 'reg':
            raise RuntimeError('Trying to print a symbol not stored in a register')

        self.print_string = print_string

    def used_variables(self):
        return [self.src]

    def human_repr(self):
        return f"{blue('print')} {self.src}"


class ReadStat(Stat):
    def __init__(self, parent=None, symtab=None):
        log_indentation(bold(f"New ReadStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)

    def lower(self):
        tmp = new_temporary(self.symtab, TYPENAMES['int'])
        read = ReadCommand(dest=tmp, symtab=self.symtab)
        stlist = StatList(children=[read], symtab=self.symtab)
        return self.parent.replace(self, stlist)


class ReadCommand(Stat):  # low-level node
    def __init__(self, parent=None, dest=None, symtab=None):
        log_indentation(bold(f"New ReadCommand Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.dest = dest
        if dest.alloct != 'reg':
            raise RuntimeError('Trying to read from a symbol not stored in a register')

    def destination(self):
        return self.dest

    def used_variables(self):
        return []

    def killed_variables(self):
        return [self.dest]

    def human_repr(self):
        return f"{blue('read')} {self.dest}"


class ReturnStat(Stat):
    def __init__(self, parent=None, children=[], symtab=None):
        log_indentation(bold(f"New ReturnStat Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)
        for child in self.children:
            child.parent = self

    def lower(self):
        stats = self.children

        function_definition = self.get_function()
        if function_definition == 'global':
            raise RuntimeError('The main function should not have return statements')

        # check that the function returns as many values as the defined ones
        if len(function_definition.returns) != len(self.children):
            raise RuntimeError('Too few or too many values are being returned')

        # put all values to return in the correct place in the stack
        for i in range(len(self.children)):
            stats.append(StoreStat(symbol=self.children[i].destination(), dest=function_definition.returns[i], symtab=self.symtab))

        stats.append(BranchStat(parent=self, target=None, symtab=self.symtab))

        stat_list = StatList(self.parent, stats, self.symtab)
        return self.parent.replace(self, stat_list)


class BranchStat(Stat):  # low-level node
    def __init__(self, parent=None, cond=None, target=None, is_call=False, negcond=False, space_needed_for_parameters=0, symtab=None):
        """cond == None -> branch always taken.
        If negcond is True and Cond != None, the branch is taken when cond is false,
        otherwise the branch is taken when cond is true.
        If is_call is True, this is a branch-and-link instruction.
        If target is None, the branch is a return and the 'target' is computed at runtime"""
        log_indentation(bold(f"New BranchStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.cond = cond
        self.negcond = negcond
        if not (self.cond is None) and self.cond.alloct != 'reg':
            raise RuntimeError('Trying to branch on a condition not stored in a register')
        self.target = target
        self.is_call = is_call
        # needed for returns -> parameters need to be popped after returning from a call
        self.space_needed_for_parameters = space_needed_for_parameters

    def used_variables(self):
        if self.cond is not None:
            return [self.cond]
        return []

    def is_unconditional(self):
        if self.cond is None:
            return True
        return False

    def human_repr(self):
        if self.target is None:
            return 'return to previous function'
        elif self.is_call:
            h = 'call'
        else:
            h = 'branch'
        if not (self.cond is None):
            c = f" on {'not ' if self.negcond else ''}{self.cond}"
        else:
            c = ''
        return f"{h}{c} to {self.target}"


class EmptyStat(Stat):  # low-level node
    pass

    def __repr__(self):
        if self.get_label() != '':
            return magenta(f"{self.get_label().name}: ")
        return 'empty statement'

    def used_variables(self):
        return []

    def human_repr(self):
        if self.get_label() != '':
            return self.get_label()
        return 'empty statement'


class LoadPtrToSym(Stat):  # low-level node
    def __init__(self, parent=None, dest=None, symbol=None, symtab=None):
        """Loads to the 'dest' symbol the location in memory (as an absolute
        address) of 'symbol'. This instruction is used as a starting point for
        lowering nodes which need any kind of pointer arithmetic."""
        log_indentation(bold(f"New LoadPtrToSym Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.symbol = symbol
        self.dest = dest
        if self.symbol.alloct == 'reg':
            raise RuntimeError('The symbol is not in memory')
        if self.dest.alloct != 'reg':
            raise RuntimeError('The destination is not to a register')

    def used_variables(self):
        return [self.symbol]

    def killed_variables(self):
        return [self.dest]

    def destination(self):
        return self.dest

    def human_repr(self):
        return f"{self.dest} {bold('<-')} &({self.symbol})"


class StoreStat(Stat):  # low-level node
    def __init__(self, parent=None, dest=None, symbol=None, killhint=None, symtab=None):
        """Stores the value in the 'symbol' temporary (register) to 'dest' which
        can be a symbol allocated in memory, or a temporary (symbol allocated to a
        register). In the first case, the store is done to the symbol itself; in
        the second case the dest symbol is used as a pointer to an arbitrary
        location in memory.
        Special cases for parameters and returns defined in the codegen"""
        log_indentation(bold(f"New StoreStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.symbol = symbol
        if self.symbol.alloct != 'reg':
            raise RuntimeError('Trying to store a value not from a register')
        self.dest = dest
        # set only for stores from register to register (mov instructions), tells which symbol this specific mov kills
        self.killhint = killhint

    def used_variables(self):
        if self.dest.alloct == 'reg':
            return [self.symbol, self.dest]
        return [self.symbol]

    def killed_variables(self):
        if self.dest.alloct == 'reg':
            if self.killhint:
                return [self.killhint]
            else:
                return []
        return [self.dest]

    def destination(self):
        return self.dest

    def human_repr(self):
        if isinstance(self.dest.stype, PointerType):
            return f"[{self.dest}] {bold('<-')} {self.symbol}"
        return f"{self.dest} {bold('<-')} {self.symbol}"


class LoadStat(Stat):  # low-level node
    def __init__(self, parent=None, dest=None, symbol=None, usehint=None, symtab=None):
        """Loads the value in symbol to dest, which must be a temporary. 'symbol'
        can be a symbol allocated in memory, or a temporary (symbol allocated to a
        register). In the first case, the value contained in the symbol itself is
        loaded; in the second case the symbol is used as a pointer to an arbitrary
        location in memory."""
        log_indentation(bold(f"New LoadStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.symbol = symbol
        self.dest = dest
        self.usehint = usehint
        if self.dest.alloct != 'reg':
            raise RuntimeError('Trying to load a value not to a register')

    def used_variables(self):
        if self.usehint:
            return [self.symbol, self.usehint]
        return [self.symbol]

    def killed_variables(self):
        return [self.dest]

    def destination(self):
        return self.dest

    def human_repr(self):
        if isinstance(self.symbol.stype, PointerType):
            return f"{self.dest} {bold('<-')} [{self.symbol}]"
        return f"{self.dest} {bold('<-')} {self.symbol}"


class LoadImmStat(Stat):  # low-level node
    def __init__(self, parent=None, dest=None, val=0, symtab=None):
        log_indentation(bold(f"New LoadImmStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.val = val
        self.dest = dest
        if self.dest.alloct != 'reg':
            raise RuntimeError('Trying to load a value not to a register')

    def used_variables(self):
        return []

    def killed_variables(self):
        return [self.dest]

    def destination(self):
        return self.dest

    def human_repr(self):
        return f"{self.dest} {bold('<-')} {self.val}"


class BinStat(Stat):  # low-level node
    def __init__(self, parent=None, dest=None, op=None, srca=None, srcb=None, symtab=None):
        log_indentation(bold(f"New BinStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.dest = dest  # symbol
        self.op = op
        self.srca = srca  # symbol
        self.srcb = srcb  # symbol
        if self.dest.alloct != 'reg':
            raise RuntimeError('The destination of the BinStat is not a register')
        if self.srca.alloct != 'reg' or self.srcb.alloct != 'reg':
            raise RuntimeError('A source of the Binstat is not a register')

    def killed_variables(self):
        return [self.dest]

    def used_variables(self):
        return [self.srca, self.srcb]

    def destination(self):
        return self.dest

    def human_repr(self):
        return f"{self.dest} {bold('<-')} {self.srca} {bold(f'{self.op}')} {self.srcb}"


class UnaryStat(Stat):  # low-level node
    def __init__(self, parent=None, dest=None, op=None, src=None, symtab=None):
        log_indentation(bold(f"New UnaryStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.dest = dest
        self.op = op
        self.src = src
        if self.dest.alloct != 'reg':
            raise RuntimeError('The destination of the UnaryStat is not a register')
        if self.src.alloct != 'reg':
            raise RuntimeError('The source of the UnaryStat is not a register')

    def killed_variables(self):
        return [self.dest]

    def used_variables(self):
        return [self.src]

    def destination(self):
        return self.dest

    def human_repr(self):
        return f"{self.dest} {bold('<-')} {bold(f'{self.op}')} {self.src}"


class StatList(Stat):  # low-level node
    def __init__(self, parent=None, children=None, symtab=None):
        log_indentation(bold(f"New StatList Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)

    def append(self, elem):
        elem.parent = self
        log_indentation(f"Appending statement {id(elem)} of type {elem.type()} to StatList {id(self)}")
        self.children.append(elem)

    def used_variables(self):
        u = []
        for c in self.children:
            u += c.used_variables()
        return u

    def get_content(self):
        content = f"Recap StatList {id(self)}: [\n"
        for n in self.children:
            content += ii(f"{n.type()}, {id(n)};\n")
        content += "]"
        return content

    def flatten(self):
        """Remove nested StatLists"""
        if type(self.parent) == StatList:
            log_indentation(green(f"Flattened {self.type()}, {id(self)} into parent {self.parent.type()}, {id(self.parent)}"))
            if self.get_label():
                emptystat = EmptyStat(self, symtab=self.symtab)
                self.children.insert(0, emptystat)
                emptystat.set_label(self.get_label())
            for c in self.children:
                c.parent = self.parent
            i = self.parent.children.index(self)
            self.parent.children = self.parent.children[:i] + self.children + self.parent.children[i + 1:]
        else:
            log_indentation(f"{red('NOT')} flattening {cyan(f'{self.type()}')}, {id(self)} into parent {cyan(f'{self.parent.type()}')}, {id(self.parent)}")

    def destination(self):
        for i in range(-1, -len(self.children) - 1, -1):
            try:
                return self.children[i].destination()
            except AttributeError:
                pass
        return None


class Block(Stat):  # low-level node
    def __init__(self, parent=None, gl_sym=None, lc_sym=None, defs=None, body=None):
        log_indentation(bold(f"New Block Node (id: {id(self)})"))
        super().__init__(parent, [], lc_sym)
        self.global_symtab = gl_sym
        self.body = body
        self.defs = defs
        self.body.parent = self
        self.defs.parent = self
        self.stackroom = 0
        # XXX: used just for printing
        self.local_symtab = lc_sym


# DEFINITIONS

class Definition(IRNode):
    def __init__(self, parent=None, symbol=None):
        log_indentation(bold(f"New Definition Node (id: {id(self)})"))
        super().__init__(parent, [], None)
        self.parent = parent
        self.symbol = symbol


class FunctionDef(Definition):
    def __init__(self, parent=None, symbol=None, parameters=[], body=None, returns=[]):
        log_indentation(bold(f"New Functions Definition Node (id: {id(self)})"))
        super().__init__(parent, symbol)
        self.body = body
        self.body.parent = self
        self.parameters = parameters
        self.returns = returns

    def get_global_symbols(self):
        return self.body.global_symtab.exclude([TYPENAMES['function'], TYPENAMES['label']])


class DefinitionList(IRNode):
    def __init__(self, parent=None, children=None):
        log_indentation(bold(f"New Definition List Node (id: {id(self)})"))
        super().__init__(parent, children, None)

    def append(self, elem):
        elem.parent = self
        self.children.append(elem)
