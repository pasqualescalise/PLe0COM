#!/usr/bin/env python3

"""Intermediate Representation

Representation of the source code, created by converting (or "lowering") all
AST nodes into single instructions. This file also contains the type definitions.

IR instructions (except definitions) need to implement a few methods:
    + __repr__, to print them in a nice concise way
    + replace_temporaries, to replace all their temporary variables with newer
      ones, unless they are already present in the "mapping" dictionary
    + __deepcopy__, specifying a method to copy them and their attributes
"""

from functools import reduce
from copy import deepcopy

from backend.codegenhelp import REGISTER_SIZE
from logger import log_indentation, ii, li, red, green, yellow, blue, magenta, cyan, bold, italic, underline


# UTILITIES

temporary_count = 0


def new_temporary(symtab, type):
    global temporary_count
    temp = Symbol(name=f"t{temporary_count}", type=type, alloct='reg', is_temporary=True)
    temporary_count += 1
    return temp


def replace_temporary_attributes(node, attributes, mapping, create_new=True):
    for attribute in attributes:
        try:
            temp = getattr(node, attribute)
        except AttributeError:
            raise RuntimeError(f"Node {node} does not have the attribute {attribute}")

        if temp.is_temporary:
            if temp in mapping:
                setattr(node, attribute, mapping[temp])
            else:
                if create_new:
                    new_temp = new_temporary(node.symtab, temp.type)
                    mapping[temp] = new_temp
                    setattr(node, attribute, new_temp)


# TYPES

class Type:
    def __init__(self, name, size, basetype, qualifiers=None, printable=False):
        # can contain 'unsigned', 'printable', 'assignable'
        if qualifiers is None:
            qualifiers = []
        self.size = size
        self.basetype = basetype
        self.qualifiers = qualifiers
        self.name = name
        self.printable = printable

    def __repr__(self):
        name = self.name
        if 'unsigned' in self.qualifiers:
            name = f"u{name}"
        return name

    def __eq__(self, other):  # strict equivalence
        if not isinstance(other, Type):
            return False

        elif self.qualifiers != other.qualifiers:
            return False

        elif self.basetype != other.basetype:
            return False

        elif self.size != other.size:
            return False

        elif self.name != other.name:
            return False

        return True

    def is_numeric(self):
        return self.basetype == "Int"

    def is_string(self):
        """A type is string if it's char[] or &char"""
        return (isinstance(self, ArrayType) and self.basetype.basetype == "Char" and len(self.dims) == 1) or (isinstance(self, PointerType) and self.pointstotype.basetype == "Char")


class ArrayType(Type):
    def __init__(self, name, dims, basetype):
        """dims is a list of dimensions: dims = [5]: array of 5 elements;
        dims = [5, 5]: 5x5 matrix; and so on"""
        self.dims = dims
        if basetype is not None:
            super().__init__(name, reduce(lambda a, b: a * b, dims) * basetype.size, basetype)
            self.name = name if name else self.default_name()
            if self.is_printable():
                self.qualifiers += ['printable']

    def default_name(self):
        return self.basetype.name + repr(self.dims)

    def is_printable(self):
        return self.is_string()

    def __repr__(self):
        return self.name


class LabelType(Type):
    def __init__(self):
        super().__init__('label', 0, 'Label', [])
        self.ids = 0

    def __call__(self, target=None):
        self.ids += 1
        return Symbol(name=f"label{self.ids}", type=self, value=target, is_temporary=True)


class FunctionType(Type):
    def __init__(self):
        super().__init__('function', 0, 'Function', [])


class PointerType(Type):  # can't define a variable as type PointerType, it's used for arrays
    def __init__(self, ptrto):
        """ptrto is the type of the object that this pointer points to."""
        super().__init__('&' + ptrto.name, REGISTER_SIZE, 'Int', ['unsigned'])
        self.pointstotype = ptrto
        if self.is_printable():
            self.qualifiers += ['printable']

    def is_printable(self):
        return self.is_string()


TYPENAMES = {
    'int': Type('int', 32, 'Int', ['printable', 'assignable']),
    'short': Type('short', 16, 'Int', ['printable', 'assignable']),
    'byte': Type('byte', 8, 'Int', ['printable', 'assignable']),

    'uint': Type('int', 32, 'Int', ['unsigned', 'printable', 'assignable']),
    'ushort': Type('short', 16, 'Int', ['unsigned', 'printable', 'assignable']),
    'ubyte': Type('byte', 8, 'Int', ['unsigned', 'printable', 'assignable']),

    'char': Type('char', 8, 'Char', ['unsigned', 'assignable']),  # TODO: should char be assignable?

    'label': LabelType(),
    'function': FunctionType(),

    'boolean': Type('boolean', 8, 'Boolean', ['printable', 'assignable']),

    'statement': Type('statement', 0, 'Statement', [])
}


# SYMBOLS

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

    def __init__(self, name, type, value=None, alloct='auto', function_symbol=None, used_in_nested_procedure=False, is_temporary=False):
        self.name = name
        self.type = type
        self.value = value  # if not None, it is a constant
        self.alloct = alloct
        self.allocinfo = None
        # useful to understand the scope of the symbol
        self.function_symbol = function_symbol
        # if a variable is used in a nested procedure in cannot be promoted to a register
        self.used_in_nested_procedure = used_in_nested_procedure
        # temporaries are special since they can be replaced easily
        self.is_temporary = is_temporary

    def set_alloc_info(self, allocinfo):
        self.allocinfo = allocinfo  # in byte

    def is_array(self):
        return isinstance(self.type, ArrayType)

    def is_monodimensional_array(self):
        return self.is_array() and len(self.type.dims) == 1

    def is_pointer(self):
        return isinstance(self.type, PointerType)

    def is_scalar(self):
        return not self.is_pointer() and not self.is_array()

    def is_numeric(self):
        return (self.type.is_numeric()) or (self.is_array() and self.type.basetype.is_numeric())

    def is_string(self):
        return self.type.is_string()

    def is_boolean(self):
        return (self.type == TYPENAMES['boolean']) or (self.is_array() and self.type.basetype == TYPENAMES['boolean'])

    def is_label(self):
        return isinstance(self.type, LabelType)

    def __repr__(self):
        res = f"{self.alloct} {self.type}"

        if self.type in [FunctionType(), LabelType()]:
            res += f" {magenta(f'{self.name}')}"
        elif self.alloct != "reg":
            res += f" {green(f'{self.name}')}"
        else:
            res += f" {red(f'{self.name}')}"
        if self.allocinfo is not None:
            res += f" {{{yellow(italic(f'{self.allocinfo}'))}}}"
        if self.value and not self.is_label():
            res += " value \"" + f"{bold(f'{self.value}')}" + "\""
        return res

    def __deepcopy__(self, memo):
        return Symbol(self.name, self.type, value=self.value, alloct=self.alloct, function_symbol=self.function_symbol, used_in_nested_procedure=self.used_in_nested_procedure, is_temporary=self.is_temporary)


class SymbolTable(list):
    def find(self, node, name):
        log_indentation(underline(f"Looking up {name}"))
        for s in self:
            if s.alloct == "param":
                # for parameters it's not enough to check the name, also
                # the called function must be the one being parsed to
                # make sure to get the correct variable in the scope
                try:
                    if s.function_symbol == node.current_function and s.name == name:
                        return s
                except AttributeError:
                    pass  # trying to use find outside of the parser
            elif s.name == name:
                try:
                    if s.function_symbol != node.current_function:
                        s.used_in_nested_procedure = True
                except AttributeError:
                    pass  # trying to use find outside of the parser
                return s
        raise RuntimeError(f"Looking up for symbol {name} in function {magenta(f'{node.current_function.name}')} failed!")

    def push(self, symbol):
        self.insert(0, symbol)

    def __repr__(self):
        res = cyan("SymbolTable") + " {\n"
        for symbol in self:
            res += f"\t{symbol}\n"
        res += "}"
        return res

    def exclude_without_qualifier(self, qualifier):
        return [symb for symb in self if qualifier in symb.type.qualifiers]

    def exclude_alloct(self, allocts):
        return [symb for symb in self if symb.alloct not in allocts]


class DataSymbolTable():
    data_symtab = SymbolTable()
    data_variables_count = 0

    @staticmethod
    def new_data_symbol(type, value):
        name = f"data{DataSymbolTable.data_variables_count}"
        DataSymbolTable.data_variables_count += 1
        data_variable = Symbol(name=name, type=type, value=value, alloct='data')
        return data_variable

    @staticmethod
    def add_data_symbol(type, value):
        found = DataSymbolTable.find_by_type_and_value(type, value)
        if found is None:
            new_symbol = DataSymbolTable.new_data_symbol(type, value)
            DataSymbolTable.data_symtab.append(new_symbol)
            return new_symbol

        return found

    @staticmethod
    def find_by_type_and_value(type, value):
        for symbol in DataSymbolTable.data_symtab:
            if symbol.type.name == type.name and symbol.value == value:
                return symbol

        return None

    @staticmethod
    def get_data_symtab():
        return DataSymbolTable.data_symtab


# IRINSTRUCTION

class IRInstruction():  # abstract
    def __init__(self, parent=None, symtab=None):
        self.symtab = symtab
        self.parent = parent
        self.label = None

    # XXX: must only be used for printing
    def type_repr(self):
        return ".".join(str(type(self)).split("'")[1].split(".")[-2:])

    def __repr__(self):
        attrs = {'body', 'symbol', 'defs', 'local_symtab', 'parameters', 'returns', 'called_by_counter'} & set(dir(self))

        res = f"{cyan(f'{self.type_repr()}')}, {id(self)}" + " {"
        if self.parent is not None:
            # res += f"\nparent: {id(self.parent)};\n"
            res += "\n"
            pass
        else:
            # a missing parent is not a bug only for the root node, but at this
            # level of abstraction there is no way to distinguish between the root
            # node and a node with a missing parent
            res += red(" MISSING PARENT\n")

        if "children" in dir(self) and len(self.children):
            res += ii("children: {\n")
            for i in range(len(self.children)):
                rep = repr(self.children[i]).split("\n")
                if isinstance(self.children[i], EmptyInstruction):
                    res += li(f"{self.children[i]}")  # label
                elif isinstance(self, InstructionList) and self.flat:
                    res += "\n".join([f"{' ' * 8}{i}: {s}" for s in rep])
                else:
                    res += "\n".join([f"{' ' * 8}{s}" for s in rep])
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

    def get_function(self):
        if not self.parent:
            return self
        elif isinstance(self.parent, FunctionDef):
            return self.parent
        else:
            return self.parent.get_function()

    def set_label(self, label):
        self.label = label
        label.value = self  # set target

    def get_label(self):
        return self.label

    # for liveness analysis
    def used_variables(self):
        return []

    # for liveness analysis
    def killed_variables(self):
        return []


class PrintInstruction(IRInstruction):
    def __init__(self, parent=None, src=None, print_type=None, newline=True, symtab=None):
        log_indentation(bold(f"New PrintInstruction Node (id: {id(self)})"))
        super().__init__(parent, symtab)
        self.src = src
        if src.alloct != 'reg':
            raise RuntimeError('Trying to print a symbol not stored in a register')

        self.print_type = print_type
        self.newline = newline

    def used_variables(self):
        return [self.src]

    def __repr__(self):
        return f"{blue('print')} {self.src}"

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['src'], mapping, create_new=create_new)

    def __deepcopy__(self, memo):
        return PrintInstruction(parent=self.parent, src=self.src, print_type=self.print_type, symtab=self.symtab)


class ReadInstruction(IRInstruction):
    def __init__(self, parent=None, dest=None, symtab=None):
        log_indentation(bold(f"New ReadInstruction Node (id: {id(self)})"))
        super().__init__(parent, symtab)
        self.dest = dest
        if dest.alloct != 'reg':
            raise RuntimeError('Trying to read from a symbol not stored in a register')

    def destination(self):
        return self.dest

    def used_variables(self):
        return []

    def killed_variables(self):
        return [self.dest]

    def __repr__(self):
        return f"{blue('read')} {self.dest}"

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['dest'], mapping, create_new=create_new)

    def __deepcopy__(self, memo):
        return ReadInstruction(parent=self.parent, dest=self.dest, symtab=self.symtab)


class BranchInstruction(IRInstruction):
    def __init__(self, parent=None, cond=None, target=None, negcond=False, parameters=[], returns=[], symtab=None):
        """cond == None -> branch always taken.
        If negcond is True and Cond != None, the branch is taken when cond is false,
        otherwise the branch is taken when cond is true.
        If the target is a function symbol, this is a branch-and-link instruction.
        If target is None, the branch is a return and the 'target' is computed at runtime"""
        log_indentation(bold(f"New BranchInstruction Node (id: {id(self)})"))
        super().__init__(parent, symtab)
        self.cond = cond
        self.negcond = negcond
        if not (self.cond is None) and self.cond.alloct != 'reg':
            raise RuntimeError('Trying to branch on a condition not stored in a register')
        self.target = target
        self.parameters = parameters
        self.returns = returns

    def used_variables(self):
        if self.is_call():
            return self.parameters
        elif self.is_return():
            return self.returns
        if self.cond is not None:
            return [self.cond]
        return []

    def killed_variables(self):
        if self.is_call():
            return [r for r in self.returns if r != "_"]
        return []

    def is_unconditional(self):
        if self.cond is None:
            return True
        return False

    def is_return(self):
        if self.target is None:
            return True
        return False

    def is_call(self):
        if isinstance(self.target, Symbol) and self.target.type == FunctionType():
            return True
        return False

    def __repr__(self):
        if self.is_return():
            r = ""
            if len(self.returns) > 0:
                r = " -> "
                r += cyan(f"({', '.join([x.name for x in self.returns])})")
            return f"return to caller{r}"
        elif self.is_call():
            h = 'call'
        else:
            h = 'branch'
        if not (self.cond is None):
            c = f" on {'not ' if self.negcond else ''}{self.cond}"
        else:
            c = ''
        if len(self.parameters) > 0:
            p = cyan(f"({', '.join([x.name for x in self.parameters])})")
        else:
            p = ''
        if len(self.returns) > 0:
            r = " -> "
            r += cyan(f"({', '.join([x.name if isinstance(x, Symbol) else x for x in self.returns])})")
        else:
            r = ''
        return f"{h}{c} to {self.target}{p}{r}"

    def replace_temporaries(self, mapping, create_new=True):
        if self.cond is not None and self.cond.is_temporary:
            if self.cond in mapping:
                self.cond = mapping[self.cond]
            else:
                if create_new:
                    new_temp = new_temporary(self.symtab, self.cond.type)
                    mapping[self.cond] = new_temp
                    self.cond = new_temp

        if self.target and not self.is_call():
            if create_new:
                new_target = TYPENAMES['label']()
                mapping[self.target] = new_target
                self.target = new_target

        new_parameters = []
        for parameter in self.parameters:
            if parameter.is_temporary:
                if parameter in mapping:
                    new_parameters.append(mapping[parameter])
                elif create_new:
                    new_parameter = new_temporary(self.symtab, parameter.type)
                    mapping[parameter] = new_parameter
                    new_parameters.append(new_parameter)
                else:
                    new_parameters.append(parameter)
            else:
                new_parameters.append(parameter)
        self.parameters = new_parameters

        new_returns = []
        for ret in self.returns:
            if ret != "_" and ret.is_temporary:
                if ret in mapping:
                    new_returns.append(mapping[ret])
                elif create_new:
                    new_return = new_temporary(self.symtab, ret.type)
                    mapping[ret] = new_return
                    new_returns.append(new_return)
                else:
                    new_returns.append(ret)
            else:
                new_returns.append(ret)
        self.returns = new_returns

    def __deepcopy__(self, memo):
        return BranchInstruction(parent=self.parent, cond=self.cond, target=self.target, negcond=self.negcond, parameters=self.parameters, returns=self.returns, symtab=self.symtab)


class EmptyInstruction(IRInstruction):
    pass

    def __repr__(self):
        if self.get_label() != '':
            return magenta(f"{self.get_label().name}: ")
        return 'empty instruction'

    def used_variables(self):
        return []

    def replace_temporaries(self, mapping, create_new=True):
        if self.get_label() != '':
            if self.get_label() in mapping:
                self.set_label(mapping[self.get_label()])
            else:
                if create_new:
                    new_label = TYPENAMES['label']()
                    mapping[self.get_label()] = new_label
                    self.set_label(new_label)

    def __deepcopy__(self, memo):
        new = EmptyInstruction(parent=self.parent, symtab=self.symtab)
        new.set_label(self.get_label())
        return new


class LoadPointerInstruction(IRInstruction):
    def __init__(self, parent=None, dest=None, symbol=None, symtab=None):
        """Loads to the 'dest' symbol the location in memory (as an absolute
        address) of 'symbol'. This instruction is used as a starting point for
        lowering nodes which need any kind of pointer arithmetic."""
        log_indentation(bold(f"New LoadPointerInstruction Node (id: {id(self)})"))
        super().__init__(parent, symtab)
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

    def __repr__(self):
        return f"{self.dest} {bold('<-')} &({self.symbol})"

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['dest', 'symbol'], mapping, create_new=create_new)

    def __deepcopy__(self, memo):
        return LoadPointerInstruction(parent=self.parent, dest=self.dest, symbol=self.symbol, symtab=self.symtab)


class StoreInstruction(IRInstruction):
    def __init__(self, parent=None, dest=None, symbol=None, killhint=None, symtab=None):
        """Stores the value in the 'symbol' temporary (register) to 'dest' which
        can be a symbol allocated in memory, or a temporary (symbol allocated to a
        register). In the first case, the store is done to the symbol itself; in
        the second case the dest symbol is used as a pointer to an arbitrary
        location in memory.
        Special cases for parameters and returns defined in the codegen"""
        log_indentation(bold(f"New StoreInstruction Node (id: {id(self)})"))
        super().__init__(parent, symtab)
        self.symbol = symbol
        if self.symbol.alloct != 'reg':
            raise RuntimeError('Trying to store a value not from a register')
        self.dest = dest
        # set only for stores from register to register (mov instructions), tells which symbol this specific mov kills
        self.killhint = killhint

    def used_variables(self):
        if self.dest.alloct == 'reg' and self.dest.is_pointer():
            return [self.symbol, self.dest]
        return [self.symbol]

    def killed_variables(self):
        if self.dest.alloct == 'reg':
            if self.killhint:  # TODO: remove this and just make it automatic
                return [self.killhint]
            else:
                return []
        return [self.dest]

    def destination(self):
        return self.dest

    def __repr__(self):
        if self.dest.is_pointer():
            return f"[{self.dest}] {bold('<-')} {self.symbol}"
        return f"{self.dest} {bold('<-')} {self.symbol}"

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['dest', 'symbol'], mapping, create_new=create_new)
        if self.killhint is not None and self.killhint.is_temporary and self.killhint in mapping:
            self.killhint = mapping[self.killhint]

    def __deepcopy__(self, memo):
        return StoreInstruction(parent=self.parent, dest=self.dest, symbol=self.symbol, killhint=self.killhint, symtab=self.symtab)


class LoadInstruction(IRInstruction):
    def __init__(self, parent=None, dest=None, symbol=None, usehint=None, symtab=None):
        """Loads the value in symbol to dest, which must be a temporary. 'symbol'
        can be a symbol allocated in memory, or a temporary (symbol allocated to a
        register). In the first case, the value contained in the symbol itself is
        loaded; in the second case the symbol is used as a pointer to an arbitrary
        location in memory."""
        log_indentation(bold(f"New LoadInstruction Node (id: {id(self)})"))
        super().__init__(parent, symtab)
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

    def __repr__(self):
        if self.symbol.is_pointer():
            return f"{self.dest} {bold('<-')} [{self.symbol}]"
        return f"{self.dest} {bold('<-')} {self.symbol}"

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['dest', 'symbol'], mapping, create_new=create_new)
        if self.usehint is not None and self.usehint.is_temporary and self.usehint in mapping:
            self.usehint = mapping[self.usehint]

    def __deepcopy__(self, memo):
        return LoadInstruction(parent=self.parent, dest=self.dest, symbol=self.symbol, usehint=self.usehint, symtab=self.symtab)


class LoadImmInstruction(IRInstruction):
    def __init__(self, parent=None, dest=None, val=0, symtab=None):
        log_indentation(bold(f"New LoadImmInstruction Node (id: {id(self)})"))
        super().__init__(parent, symtab)
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

    def __repr__(self):
        return f"{self.dest} {bold('<-')} {self.val}"

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['dest'], mapping, create_new=create_new)

    def __deepcopy__(self, memo):
        return LoadImmInstruction(parent=self.parent, dest=self.dest, val=self.val, symtab=self.symtab)


class BinaryInstruction(IRInstruction):
    def __init__(self, parent=None, dest=None, op=None, srca=None, srcb=None, symtab=None):
        log_indentation(bold(f"New BinaryInstruction Node (id: {id(self)})"))
        super().__init__(parent, symtab)
        self.dest = dest  # symbol
        self.op = op
        self.srca = srca  # symbol
        self.srcb = srcb  # symbol
        if self.dest.alloct != 'reg':
            raise RuntimeError('The destination of the BinaryInstruction is not a register')
        if self.srca.alloct != 'reg' or self.srcb.alloct != 'reg':
            raise RuntimeError('A source of the BinaryInstruction is not a register')

    def killed_variables(self):
        return [self.dest]

    def used_variables(self):
        return [self.srca, self.srcb]

    def destination(self):
        return self.dest

    def __repr__(self):
        return f"{self.dest} {bold('<-')} {self.srca} {bold(f'{self.op}')} {self.srcb}"

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['dest', 'srca', 'srcb'], mapping, create_new=create_new)

    def __deepcopy__(self, memo):
        return BinaryInstruction(parent=self.parent, dest=self.dest, op=self.op, srca=self.srca, srcb=self.srcb, symtab=self.symtab)


class UnaryInstruction(IRInstruction):
    def __init__(self, parent=None, dest=None, op=None, src=None, symtab=None):
        log_indentation(bold(f"New UnaryInstruction Node (id: {id(self)})"))
        super().__init__(parent, symtab)
        self.dest = dest
        self.op = op
        self.src = src
        if self.dest.alloct != 'reg':
            raise RuntimeError('The destination of the UnaryInstruction is not a register')
        if self.src.alloct != 'reg':
            raise RuntimeError('The source of the UnaryInstruction is not a register')

    def killed_variables(self):
        return [self.dest]

    def used_variables(self):
        return [self.src]

    def destination(self):
        return self.dest

    def __repr__(self):
        return f"{self.dest} {bold('<-')} {bold(f'{self.op}')} {self.src}"

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['dest', 'src'], mapping, create_new=create_new)

    def __deepcopy__(self, memo):
        return UnaryInstruction(parent=self.parent, dest=self.dest, op=self.op, src=self.src, symtab=self.symtab)


class InstructionList(IRInstruction):
    def __init__(self, parent=None, children=None, flat=False, symtab=None):
        log_indentation(bold(f"New InstructionList Node (id: {id(self)})"))
        super().__init__(parent, symtab)
        if children:
            self.children = children
            for child in children:
                child.parent = self
        else:
            self.children = []
        # when printing, print line numbers of flattened InstructionLists
        self.flat = flat

    def used_variables(self):
        u = []
        for c in self.children:
            u += c.used_variables()
        return u

    def destination(self):
        for i in range(-1, -len(self.children) - 1, -1):
            try:
                return self.children[i].destination()
            except AttributeError:
                pass
        return None

    def remove(self, instruction):
        try:
            self.children.remove(instruction)
        except ValueError:
            raise RuntimeError(f"Can't find instruction '{instruction}' to remove in InstructionList {id(self)}")

    def flatten(self):
        """Remove nested InstructionLists"""
        for child in self.children:
            try:
                child.flatten()
            except AttributeError:
                pass

        if isinstance(self.parent, InstructionList):
            log_indentation(green(f"Flattened {self.type_repr()}, {id(self)} into parent {self.parent.type_repr()}, {id(self.parent)}"))
            if self.get_label():
                empty = EmptyInstruction(self, symtab=self.symtab)
                self.children.insert(0, empty)
                empty.set_label(self.get_label())
            for c in self.children:
                c.parent = self.parent
            try:
                i = self.parent.children.index(self)
            except Exception as e:
                print(e)
            self.parent.children = self.parent.children[:i] + self.children + self.parent.children[i + 1:]
        else:
            log_indentation(f"{red('NOT')} flattening {cyan(f'{self.type_repr()}')}, {id(self)} into parent {cyan(f'{self.parent.type_repr()}')}, {id(self.parent)}")
            self.flat = True

    def replace_temporaries(self, mapping, create_new=True):
        for child in self.children:
            child.replace_temporaries(mapping, create_new)

    def __deepcopy__(self, memo):
        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return InstructionList(parent=self.parent, children=new_children, flat=self.flat, symtab=self.symtab)


class Block(IRInstruction):
    def __init__(self, parent=None, gl_sym=None, lc_sym=None, defs=None, body=None):
        log_indentation(bold(f"New Block Node (id: {id(self)})"))
        super().__init__(parent, lc_sym)
        self.global_symtab = gl_sym
        self.body = body
        self.defs = defs
        self.body.parent = self
        self.defs.parent = self
        self.stackroom = 0
        # XXX: used just for printing
        self.local_symtab = lc_sym

    def replace_temporaries(self, mapping, create_new=True):
        pass

    def __deepcopy__(self, memo):
        new_body = deepcopy(self.body, memo)
        new_defs = deepcopy(self.defs, memo)

        return Block(parent=self.parent, gl_sym=self.global_symtab, lc_sym=self.local_symtab, defs=new_defs, body=new_body)


# DEFINITIONS

class FunctionDef(IRInstruction):
    def __init__(self, parent=None, symbol=None, parameters=[], body=None, returns=[], called_by_counter=0):
        log_indentation(bold(f"New Functions Definition Node (id: {id(self)})"))
        super().__init__(parent, None)
        self.symbol = symbol
        self.body = body
        self.body.parent = self
        self.parameters = parameters
        self.returns = returns
        self.called_by_counter = called_by_counter

    def get_global_symbols(self):
        return self.body.global_symtab.exclude_without_qualifier('assignable')

    def __deepcopy__(self, memo):
        new_body = deepcopy(self.body, memo)

        return FunctionDef(parent=self.parent, symbol=self.symbol, parameters=self.parameters, body=new_body, returns=self.returns, called_by_counter=self.called_by_counter)


class DefinitionList(IRInstruction):
    def __init__(self, parent=None, children=None):
        log_indentation(bold(f"New Definition List Node (id: {id(self)})"))
        super().__init__(parent, None)
        if children:
            self.children = children
            for child in children:
                child.parent = self
        else:
            self.children = []

    def append(self, elem):
        if not isinstance(elem, FunctionDef):
            raise RuntimeError(f"Trying to append node {id(elem)} of type {elem.type_repr()} to DefinitionList {id(self)}, that can only contatin FunctionDefs")
        elem.parent = self
        self.children.append(elem)

    def remove(self, elem):
        self.children.remove(elem)

    def __deepcopy__(self, memo):
        return DefinitionList(parent=self.parent, children=self.children)
