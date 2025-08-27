#!/usr/bin/env python3

"""Intermediate Representation
Could be improved by relying less on class hierarchy and more on string tags
and/or duck typing. Includes lowering and flattening functions. Every node must
have a lowering function or a code generation function (codegen functions are
in a separate module though).

There are two types of nodes: high and low level. The parser usually produces
only high-level nodes; all high-level nodes implement the "lower" method, that
converts the node into a StatList of low-level nodes. All of this StatLists are
successively flattened. Low-level nodes need to implement a few methods:
    + human_repr, to print them in a nice concise way
    + replace_temporaries, to replace all their temporary variables with newer
      ones, unless they are already present in the "mapping" dictionary
    + __deepcopy__, to present what to do when the copy.deepcopy() method is
      called on the node; usually just recreate the node, but not its symbols
"""

from functools import reduce
from copy import deepcopy
from math import log

from codegenhelp import REGISTER_SIZE
from logger import log_indentation, ii, li, red, green, yellow, blue, magenta, cyan, bold, italic, underline
import logger

# UTILITIES

UNARY_CONDITIONALS = ['odd']
BINARY_CONDITIONALS = ['eql', 'neq', 'lss', 'leq', 'gtr', 'geq']

temporary_count = 0
data_variables_count = 0


def new_temporary(symtab, type):
    global temporary_count
    temp = Symbol(name=f"t{temporary_count}", stype=type, alloct='reg', is_temporary=True)
    temporary_count += 1
    return temp


def new_variable_name():
    global data_variables_count
    name = f"data{data_variables_count}"
    data_variables_count += 1
    return name


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
                    new_temp = new_temporary(node.symtab, temp.stype)
                    mapping[temp] = new_temp
                    setattr(node, attribute, new_temp)


# TYPES

class Type:
    def __init__(self, name, size, basetype, qualifiers=None):
        if qualifiers is None:
            qualifiers = []
        self.size = size
        self.basetype = basetype
        self.qualifiers = qualifiers
        self.name = name if name else self.default_name()

    def default_name(self):
        n = ''
        if 'unsigned' in self.qualifiers:
            n += 'u'
        n += 'int'  # no float types exist at the moment
        return n

    def is_numeric(self):
        return self.basetype == "Int"


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
        return Symbol(name=f"label{self.ids}", stype=self, value=target, is_temporary=True)


class FunctionType(Type):
    def __init__(self):
        super().__init__('function', 0, 'Function', [])


class PointerType(Type):  # can't define a variable as type PointerType, it's used for arrays
    def __init__(self, ptrto):
        """ptrto is the type of the object that this pointer points to."""
        super().__init__('&' + ptrto.name, REGISTER_SIZE, 'Int', ['unsigned'])
        self.pointstotype = ptrto


class BooleanType(Type):
    def __init__(self):
        super().__init__('boolean', 8, 'Boolean', [])


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

    'boolean': BooleanType(),
}


# Returns statements that mask shorts and bytes, to eliminate sign extension
def mask_numeric(operand, symtab):
    mask = [int(0x000000ff), int(0x0000ffff)][operand.stype.size // 8 - 1]  # either byte or short
    mask_temp = new_temporary(symtab, TYPENAMES['int'])
    load_mask = LoadImmStat(dest=mask_temp, val=mask, symtab=symtab)
    apply_mask = BinStat(dest=operand, op="and", srca=operand, srcb=load_mask.destination(), symtab=symtab)
    return [load_mask, apply_mask]


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

    def __init__(self, name, stype, value=None, alloct='auto', fname='', used_in_nested_procedure=False, is_temporary=False):
        self.name = name
        self.stype = stype
        self.value = value  # if not None, it is a constant
        self.alloct = alloct
        self.allocinfo = None
        # useful to understand the scope of the symbol
        self.fname = fname
        # if a variable is used in a nested procedure in cannot be promoted to a register
        self.used_in_nested_procedure = used_in_nested_procedure
        # temporaries are special since they can be replaced easily
        self.is_temporary = is_temporary

    def set_alloc_info(self, allocinfo):
        self.allocinfo = allocinfo  # in byte

    def is_array(self):
        return isinstance(self.stype, ArrayType)

    def is_pointer(self):
        return isinstance(self.stype, PointerType)

    def is_scalar(self):
        return not self.is_pointer() and not self.is_array()

    def is_numeric(self):
        return (self.stype.is_numeric()) or (self.is_array() and self.stype.basetype.is_numeric())

    def is_string(self):
        """A Symbol references a string if it's of type char[] or &char"""
        return (self.is_array() and self.stype.basetype.name == "char") or (isinstance(self.stype, PointerType) and self.stype.pointstotype.name == "char")

    def is_boolean(self):
        return isinstance(self.stype, BooleanType) or (self.is_array() and isinstance(self.stype.basetype, BooleanType))

    def __repr__(self):
        base = f"{self.alloct} {self.stype.name}"

        if isinstance(self.stype, (FunctionType, LabelType)):
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

    def push(self, symbol):
        self.insert(0, symbol)

    def __repr__(self):
        res = f"{cyan('SymbolTable')} " + '{\n'
        for symbol in self:
            res += f"\t{symbol}\n"
        res += "}"
        return res

    def exclude(self, barred_types):
        return [symb for symb in self if symb.stype not in barred_types]

    def exclude_alloct(self, allocts):
        return [symb for symb in self if symb.alloct not in allocts]


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

        attrs = {'body', 'cond', 'value', 'thenpart', 'elifspart', 'elsepart', 'symbol', 'call', 'init', 'step', 'expr', 'target', 'defs', 'local_symtab', 'offset', 'function_symbol', 'parameters', 'returns', 'called_by_counter', 'epilogue', 'values'} & set(dir(self))

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
            child_index = 0
            for child in self.children:
                if isinstance(child, EmptyStat):
                    res += li(f"{child}\n")  # label
                else:
                    rep = repr(child).split("\n")
                    if isinstance(self, StatList) and self.flat:
                        res += "\n".join([f"{' ' * 8}{child_index}: {s}" for s in rep])
                    else:
                        res += "\n".join([f"{' ' * 8}{s}" for s in rep])
                    res += "\n"
                child_index += 1
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

    # XXX: must only be used for printing
    def type(self):
        return str(type(self)).split("'")[1]

    def navigate(self, action, *args, quiet=False):
        attrs = ['defs', 'body', 'cond', 'value', 'thenpart', 'elifspart', 'elsepart', 'symbol', 'call', 'init', 'step', 'expr', 'target', 'global_symtab', 'local_symtab', 'offset', 'epilogue']
        attrs = [x for x in attrs if x in set(dir(self))]

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
        attrs = {'body', 'cond', 'value', 'thenpart', 'elifspart', 'elsepart', 'symbol', 'call', 'init', 'step', 'expr', 'target', 'defs', 'global_symtab', 'local_symtab', 'offset', 'epilogue'} & set(dir(self))

        for d in attrs:
            try:
                if getattr(self, d) == old:
                    setattr(self, d, new)
                    return True
            except AttributeError:
                pass
        return False

    def get_function(self):
        if not self.parent:
            return 'main'
        elif isinstance(self.parent, FunctionDef):
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
    def get_function_definition(self, target_function_symbol):
        current_function = self.get_function()

        # it's the main function
        if current_function == 'main':
            program = self.find_the_program()
            for definition in program.defs.children:
                if definition.symbol == target_function_symbol:
                    return definition

            if current_function == 'main':
                raise RuntimeError(f"Can't find function definition of function {target_function_symbol}")

        # it's the current function
        if current_function.symbol == target_function_symbol:
            return current_function

        # it's one of the functions defined in the current function
        for definition in current_function.body.defs.children:
            if definition.symbol == target_function_symbol:
                return definition

        # it's a function defined in the parent
        return current_function.get_function_definition(target_function_symbol)

    def get_label(self):
        raise NotImplementedError

    def human_repr(self):
        raise NotImplementedError


# CONST and VAR

class Const(IRNode):
    def __init__(self, parent=None, value=0, symbol=None, symtab=None):
        log_indentation(bold(f"New Const Node (id: {id(self)})"))
        super().__init__(parent, None, symtab)
        self.value = value
        self.symbol = symbol

    def lower(self):  # TODO: make it possible to define constant booleans
        if self.value in ["True", "False"]:
            new = new_temporary(self.symtab, TYPENAMES['boolean'])
            loadst = LoadImmStat(dest=new, val=self.value, symtab=self.symtab)
        elif self.symbol is None:
            new = new_temporary(self.symtab, TYPENAMES['int'])
            loadst = LoadImmStat(dest=new, val=self.value, symtab=self.symtab)
        else:
            new = new_temporary(self.symtab, self.symbol.stype)
            loadst = LoadStat(dest=new, symbol=self.symbol, symtab=self.symtab)
        return self.parent.replace(self, StatList(children=[loadst], symtab=self.symtab))

    def __deepcopy__(self, memo):
        return Const(parent=self.parent, value=self.value, symbol=self.symbol, symtab=self.symtab)


class Var(IRNode):
    """loads in a temporary the value pointed to by the symbol"""

    def __init__(self, parent=None, var=None, symtab=None):
        log_indentation(bold(f"New Var Node (id: {id(self)})"))
        super().__init__(parent, None, symtab)
        self.symbol = var

    def used_variables(self):
        return [self.symbol]

    def lower(self):
        if self.symbol.is_string() and self.symbol.alloct != 'param':  # load strings as char pointers
            ptrreg = new_temporary(self.symtab, PointerType(self.symbol.stype.basetype))
            loadptr = LoadPtrToSym(dest=ptrreg, symbol=self.symbol, symtab=self.symtab)
            return self.parent.replace(self, StatList(children=[loadptr], symtab=self.symtab))

        elif self.symbol.is_array() and self.symbol.alloct != 'param':  # load arrays as pointers
            ptrreg = new_temporary(self.symtab, PointerType(PointerType(self.symbol.stype.basetype)))
            loadptr = LoadPtrToSym(dest=ptrreg, symbol=self.symbol, symtab=self.symtab)
            return self.parent.replace(self, StatList(children=[loadptr], symtab=self.symtab))

        new = new_temporary(self.symtab, self.symbol.stype)
        loadst = LoadStat(dest=new, symbol=self.symbol, symtab=self.symtab)
        return self.parent.replace(self, StatList(children=[loadst], symtab=self.symtab))

    def __deepcopy__(self, memo):
        return Var(parent=self.parent, var=self.symbol, symtab=self.symtab)


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
        dest = new_temporary(self.symtab, self.symbol.stype.basetype)
        off = self.offset.destination()

        statl = [self.offset]

        if self.symbol.alloct == 'param':
            # pass by reference, we have to deallocate the pointer twice
            parameter = new_temporary(self.symtab, PointerType(PointerType(self.symbol.stype.basetype)))
            loadparameter = LoadPtrToSym(dest=parameter, symbol=self.symbol, symtab=self.symtab)

            array_pointer = new_temporary(self.symtab, PointerType(self.symbol.stype.basetype))
            loadptr = LoadStat(dest=array_pointer, symbol=parameter, symtab=self.symtab)
            statl += [loadparameter, loadptr]
        else:
            array_pointer = new_temporary(self.symtab, PointerType(self.symbol.stype.basetype))
            loadptr = LoadPtrToSym(dest=array_pointer, symbol=self.symbol, symtab=self.symtab)

            statl += [loadptr]

        src = new_temporary(self.symtab, PointerType(self.symbol.stype.basetype))
        add = BinStat(dest=src, op='plus', srca=array_pointer, srcb=off, symtab=self.symtab)
        statl += [add]

        statl += [LoadStat(dest=dest, symbol=src, symtab=self.symtab)]
        return self.parent.replace(self, StatList(children=statl, symtab=self.symtab))

    def __deepcopy__(self, memo):
        new_offset = deepcopy(self.offset, memo)
        return ArrayElement(parent=self.parent, var=self.symbol, offset=new_offset, symtab=self.symtab)


class String(IRNode):
    """Puts a fixed string in the data SymbolTable"""

    def __init__(self, parent=None, value="", symtab=None):
        log_indentation(bold(f"New String Node (id: {id(self)})"))
        super().__init__(parent, None, symtab)
        self.value = value

    def used_variables(self):
        return []

    def lower(self):
        # put the string in the data SymbolTable
        data_variable = Symbol(name=new_variable_name(), stype=ArrayType(None, [len(self.value) + 1], TYPENAMES['char']), value=self.value, alloct='data')
        DataSymbolTable.add_data_symbol(data_variable)

        # load the fixed data string address
        ptrreg_data = new_temporary(self.symtab, PointerType(data_variable.stype.basetype))
        access_string = LoadPtrToSym(dest=ptrreg_data, symbol=data_variable, symtab=self.symtab)

        return self.parent.replace(self, StatList(children=[access_string], symtab=self.symtab))

    def __deepcopy__(self, memo):
        return String(parent=self.parent, value=self.value, symtab=self.symtab)


class StaticArray(IRNode):
    # XXX: this doesn't get lowered, other nodes expand themselves and
    #      access the array values one by one

    def __init__(self, parent=None, values=[], type=None, size=[], symtab=None):
        log_indentation(bold(f"New StaticArray Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.values_type = type
        self.values = values
        for value in self.values:
            value.parent = self

        if size == []:
            self.size = [len(self.values)]
        else:
            self.size = [len(self.values)] + size


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
        stats = [self.children[1], self.children[2]]

        srca = self.children[1].destination()
        srcb = self.children[2].destination()

        # type checking
        if srca.stype.name == srcb.stype.name:
            desttype = TYPENAMES[srca.stype.name]
        elif srca.stype.is_numeric() and srcb.stype.is_numeric():  # apply a mask to the smallest operand
            smallest_operand = srca if srca.stype.size < srcb.stype.size else srcb
            biggest_operand = srca if srca.stype.size > srcb.stype.size else srcb
            stats += mask_numeric(smallest_operand, self.symtab)
            desttype = Type(biggest_operand.stype.name, biggest_operand.stype.size, 'Int')
        else:
            raise RuntimeError(f"Trying to operate on two factors of different types ({srca.stype.name} and {srcb.stype.name})")

        if ('unsigned' in srca.stype.qualifiers) and ('unsigned' in srcb.stype.qualifiers):
            desttype.qualifiers += ['unsigned']

        if self.children[0] in BINARY_CONDITIONALS:
            dest = new_temporary(self.symtab, TYPENAMES['boolean'])
        else:
            dest = new_temporary(self.symtab, desttype)

        if self.children[0] not in ["slash", "mod"]:
            stmt = BinStat(dest=dest, op=self.children[0], srca=srca, srcb=srcb, symtab=self.symtab)
            stats += [stmt]
            return self.parent.replace(self, StatList(children=stats, symtab=self.symtab))

        elif self.children[0] == "mod":
            """
            try to see at compile time if the dividend of
            the modulus is a power of two:

            + if it is, there is a codegen implementation
            + if we don't know, implement the modulus as a while loop
              so that `res = op1 % op2`
              becomes something like

              while (op1 >= op2) {
                  op1 = op1 - op2;
              }
              res = op1;
            """
            if isinstance(self.children[2].children[0], LoadImmStat) and log(self.children[2].children[0].val, 2).is_integer():
                stmt = BinStat(dest=dest, op="mod", srca=srca, srcb=srcb, symtab=self.symtab)
                stats += [stmt]
                return self.parent.replace(self, StatList(children=stats, symtab=self.symtab))

            condition_variable = new_temporary(self.symtab, TYPENAMES['int'])
            loop_condition = BinStat(dest=condition_variable, op='geq', srca=srca, srcb=srcb, symtab=self.symtab)

            diff = BinStat(dest=srca, op='minus', srca=srca, srcb=srcb, symtab=self.symtab)
            loop_body = StatList(children=[diff], symtab=self.symtab)

            while_loop = WhileStat(cond=loop_condition, body=loop_body, symtab=self.symtab)

            result_store = StoreStat(dest=dest, symbol=srca, killhint=dest, symtab=self.symtab)

            stats += [while_loop, result_store]
            statl = StatList(children=stats, symtab=self.symtab)

            # XXX: we need to lower it manually since it didn't exist before
            while_loop.lower()

            return self.parent.replace(self, statl)

        elif self.children[0] == "slash":
            """
            implement the division as a while loop
            so that `res = op1 / op2`
            becomes something like

            res = 0;
            while (op2 >= op1) {
                op2 = op2 - op1;
                res++;
            }
            """
            zero_destination = LoadImmStat(dest=dest, val=0, symtab=self.symtab)

            one = new_temporary(self.symtab, TYPENAMES['int'])
            load_one = LoadImmStat(dest=one, val=1, symtab=self.symtab)

            condition_variable = new_temporary(self.symtab, TYPENAMES['int'])
            loop_condition = BinStat(dest=condition_variable, op="geq", srca=srca, srcb=srcb, symtab=self.symtab)

            op2_update = BinStat(dest=srca, op="minus", srca=srca, srcb=srcb, symtab=self.symtab)
            calc_result = BinStat(dest=dest, op="plus", srca=dest, srcb=one, symtab=self.symtab)
            loop_body = StatList(children=[op2_update, calc_result], symtab=self.symtab)

            while_loop = WhileStat(cond=loop_condition, body=loop_body, symtab=self.symtab)

            stats += [zero_destination, load_one, while_loop]
            statl = StatList(children=stats, symtab=self.symtab)

            # XXX: we need to lower it manually since it didn't exist before
            while_loop.lower()

            return self.parent.replace(self, statl)

    def __deepcopy__(self, memo):
        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return BinExpr(parent=self.parent, children=new_children, symtab=self.symtab)


class UnExpr(Expr):
    def __init__(self, parent=None, children=None, symtab=None):
        log_indentation(bold(f"New UnExpr Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)

    def get_operand(self):
        return self.children[1]

    def lower(self):
        src = self.children[1].destination()
        if self.children[0] in UNARY_CONDITIONALS:
            dest = new_temporary(self.symtab, TYPENAMES['boolean'])
        else:
            dest = new_temporary(self.symtab, src.stype)
        stmt = UnaryStat(dest=dest, op=self.children[0], src=src, symtab=self.symtab)
        statl = [self.children[1], stmt]
        return self.parent.replace(self, StatList(children=statl, symtab=self.symtab))

    def __deepcopy__(self, memo):
        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return UnExpr(parent=self.parent, children=new_children, symtab=self.symtab)


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


class CallStat(Stat):
    """Procedure call"""

    def __init__(self, parent=None, function_symbol=None, parameters=[], returns=[], symtab=None):
        log_indentation(bold(f"New CallStat Node (id: {id(self)})"))
        super().__init__(parent, parameters, symtab)
        self.function_symbol = function_symbol
        self.returns = returns

    def used_variables(self):
        return self.call.used_variables() + self.symtab.exclude([TYPENAMES['function'], TYPENAMES['label']])

    # raises RuntimeError if the number of parameters or of returns is wrong
    # TODO: add type checking
    def check_parameters_and_returns(self, function_definition):
        if len(function_definition.parameters) > len(self.children):
            raise RuntimeError(f"Passing too few parameters calling function {self.function_symbol.name}")
        if len(function_definition.parameters) < len(self.children):
            raise RuntimeError(f"Passing too many parameters calling function {self.function_symbol.name}")

        if len(function_definition.returns) > len(self.returns):
            raise RuntimeError(f"Too few values are being returned from function {function_definition.symbol.name}")
        elif len(function_definition.returns) < len(self.returns):
            raise RuntimeError(f"Too many values are being returned from function {function_definition.symbol.name}")

    def lower(self):
        function_definition = self.get_function_definition(self.function_symbol)
        function_definition.called_by_counter += 1

        self.check_parameters_and_returns(function_definition)

        parameters = [x.destination() for x in self.children]

        rets = []
        if len(self.returns) > 0:
            # XXX: self.returns_storage is created in the pre-lowering phase and it's
            #      a list with the temporaries that will contain the return values
            j = 0
            for i in range(len(self.returns)):
                if self.returns[i][0] == "_":
                    rets.append("_")
                else:
                    rets.append(self.returns_storage[j])
                    j += 1

        branch = BranchStat(target=self.function_symbol, parameters=parameters, returns=rets, symtab=self.symtab)

        stats = self.children + [branch]

        return self.parent.replace(self, StatList(children=stats, symtab=self.symtab))

    def __deepcopy__(self, memo):
        new_parameters = []
        for parameter in self.children:
            new_parameters.append(deepcopy(parameter, memo))

        new_function_symbol = deepcopy(self.function_symbol, memo)  # TODO: isn't this wrong?
        return CallStat(parent=self.parent, function_symbol=new_function_symbol, parameters=new_parameters, returns=self.returns, symtab=self.symtab)


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
        if len(self.elifspart.children) == 0 and not self.elsepart:
            branch_to_exit = BranchStat(cond=self.cond.destination(), target=exit_label, negcond=True, symtab=self.symtab)
            stat_list = StatList(self.parent, [self.cond, branch_to_exit, self.thenpart, exit_stat], self.symtab)
            return self.parent.replace(self, stat_list)

        then_label = TYPENAMES['label']()
        self.thenpart.set_label(then_label)
        branch_to_then = BranchStat(cond=self.cond.destination(), target=then_label, symtab=self.symtab)
        branch_to_exit = BranchStat(target=exit_label, symtab=self.symtab)
        no_exit_label = False  # decides whether or not to put the label at the end

        stats = [self.cond, branch_to_then]

        # elifs branches
        for i in range(0, len(self.elifspart.children), 2):
            elif_label = TYPENAMES['label']()
            self.elifspart.children[i + 1].set_label(elif_label)
            branch_to_elif = BranchStat(cond=self.elifspart.children[i].destination(), target=elif_label, symtab=self.symtab)
            stats = stats[:] + [self.elifspart.children[i], branch_to_elif]

        # NOTE: in general, avoid putting an exit label and a branch to it if the
        #       last instruction is a return

        # else
        if self.elsepart:
            last_else_instruction = self.elsepart.children[0].children[-1]
            if isinstance(last_else_instruction, BranchStat) and last_else_instruction.is_return():
                stats = stats[:] + [self.elsepart]
                no_exit_label = True
            else:
                stats = stats[:] + [self.elsepart, branch_to_exit]

        stats.append(self.thenpart)
        last_then_instruction = self.thenpart.children[0].children[-1]
        if not (isinstance(last_then_instruction, BranchStat) and last_then_instruction.is_return()):
            stats.append(branch_to_exit)

        # elifs statements
        for i in range(0, len(self.elifspart.children), 2):
            elifspart = self.elifspart.children[i + 1]
            last_elif_instruction = elifspart.children[0].children[-1]

            if isinstance(last_elif_instruction, BranchStat) and last_elif_instruction.is_return():
                stats = stats[:] + [elifspart]
                no_exit_label &= True
            else:
                stats = stats[:] + [elifspart, branch_to_exit]
                no_exit_label &= False  # if a single elif needs the exit label, put it there

        if not no_exit_label:
            stats.append(exit_stat)

        stat_list = StatList(self.parent, stats, self.symtab)
        return self.parent.replace(self, stat_list)

    def __deepcopy__(self, memo):
        cond = deepcopy(self.cond, memo)
        thenpart = deepcopy(self.thenpart, memo)
        elifspart = deepcopy(self.elifspart, memo)
        elsepart = deepcopy(self.elsepart, memo)
        return IfStat(parent=self.parent, cond=cond, thenpart=thenpart, elifspart=elifspart, elsepart=elsepart, symtab=self.symtab)


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

    def __deepcopy__(self, memo):
        new_cond = deepcopy(self.cond, memo)
        new_body = deepcopy(self.body, memo)
        return WhileStat(parent=self.parent, cond=new_cond, body=new_body, symtab=self.symtab)


class ForStat(Stat):
    def __init__(self, parent=None, init=None, cond=None, step=None, body=None, epilogue=None, symtab=None):
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

        self.epilogue = epilogue
        if self.epilogue is not None:
            self.epilogue.parent = self

    def lower(self):
        entry_label = TYPENAMES['label']()
        exit_label = TYPENAMES['label']()
        exit_stat = EmptyStat(self.parent, symtab=self.symtab)
        exit_stat.set_label(exit_label)
        self.cond.set_label(entry_label)
        branch = BranchStat(cond=self.cond.destination(), target=exit_label, negcond=True, symtab=self.symtab)
        loop = BranchStat(target=entry_label, symtab=self.symtab)
        stat_list = StatList(self.parent, [self.init, self.cond, branch, self.body, self.step, loop, exit_stat], self.symtab)

        if self.epilogue is not None:
            stat_list.append(self.epilogue)

        return self.parent.replace(self, stat_list)

    def __deepcopy__(self, memo):
        new_init = deepcopy(self.init, memo)
        new_cond = deepcopy(self.cond, memo)
        new_step = deepcopy(self.step, memo)
        new_body = deepcopy(self.body, memo)
        new_epilogue = deepcopy(self.epilogue, memo)
        return ForStat(parent=self.parent, init=new_init, cond=new_cond, step=new_step, body=new_body, epilogue=new_epilogue, symtab=self.symtab)


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
        if self.children != []:  # if it has children, it means it has been expanded
            stats = self.children
            return self.parent.replace(self, StatList(children=stats, symtab=self.symtab))

        dst = self.symbol

        # XXX: self.expr coud be a temporary
        try:
            src = self.expr.destination()
            stats = [self.expr]
        except AttributeError as e:
            if self.expr.is_temporary:
                src = self.expr
                stats = []
            else:
                raise e

        if not dst.is_string():
            if self.offset:  # TODO: this is the same as ArrayElement, but with a store instead of a load, merge the two
                stats += [self.offset]

                off = self.offset.destination()
                desttype = dst.stype
                if isinstance(desttype, ArrayType):  # this is always true at the moment
                    desttype = desttype.basetype

                if self.symbol.alloct == 'param' or self.symbol.is_string():
                    # pass by reference, we have to deallocate the pointer twice
                    parameter = new_temporary(self.symtab, PointerType(PointerType(self.symbol.stype.basetype)))
                    loadparameter = LoadPtrToSym(dest=parameter, symbol=self.symbol, symtab=self.symtab)

                    array_pointer = new_temporary(self.symtab, PointerType(desttype))
                    loadptr = LoadStat(dest=array_pointer, symbol=parameter, symtab=self.symtab)
                    stats += [loadparameter, loadptr]
                else:
                    array_pointer = new_temporary(self.symtab, PointerType(self.symbol.stype.basetype))
                    loadptr = LoadPtrToSym(dest=array_pointer, symbol=self.symbol, symtab=self.symtab)

                    stats += [loadptr]

                dst = new_temporary(self.symtab, PointerType(desttype))
                add = BinStat(dest=dst, op='plus', srca=array_pointer, srcb=off, symtab=self.symtab)
                stats += [add]

            if dst.is_temporary and not dst.is_scalar():
                stats += [StoreStat(dest=dst, symbol=src, killhint=dst, symtab=self.symtab)]
            else:
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
        dest = new_temporary(self.symtab, TYPENAMES['boolean'])
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

        # XXX: we need to lower it manually since it didn't exist before
        while_loop.lower()

        return self.parent.replace(self, statl)

    def __deepcopy__(self, memo):
        new_expr = deepcopy(self.expr, memo)
        return AssignStat(parent=self.parent, target=self.symbol, offset=self.offset, expr=new_expr, symtab=self.symtab)


class PrintStat(Stat):
    def __init__(self, parent=None, expr=None, symtab=None):
        log_indentation(bold(f"New PrintStat Node (id: {id(self)})"))
        super().__init__(parent, [expr], symtab)

    def used_variables(self):
        return self.children[0].used_variables()

    def lower(self):
        if len(self.children) > 1:
            stats = self.children
            return self.parent.replace(self, StatList(children=stats, symtab=self.symtab))

        print_type = TYPENAMES['int']  # TODO: do something for short and byte

        if self.children[0] and self.children[0].destination().is_string():
            print_type = TYPENAMES['char']
        elif self.children[0] and self.children[0].destination().is_boolean():
            print_type = TYPENAMES['boolean']
        elif self.children[0] and self.children[0].destination().is_numeric() and self.children[0].destination().stype.size == 16 and 'unsigned' in self.children[0].destination().stype.qualifiers:
            print_type = TYPENAMES['ushort']
        elif self.children[0] and self.children[0].destination().is_numeric() and self.children[0].destination().stype.size == 8 and 'unsigned' in self.children[0].destination().stype.qualifiers:
            print_type = TYPENAMES['ubyte']
        elif self.children[0] and self.children[0].destination().is_numeric() and self.children[0].destination().stype.size == 16:
            print_type = TYPENAMES['short']
        elif self.children[0] and self.children[0].destination().is_numeric() and self.children[0].destination().stype.size == 8:
            print_type = TYPENAMES['byte']

        pc = PrintCommand(src=self.children[0].destination(), print_type=print_type, symtab=self.symtab)
        stlist = StatList(children=[self.children[0], pc], symtab=self.symtab)
        return self.parent.replace(self, stlist)

    def __deepcopy__(self, memo):
        new_expr = deepcopy(self.children[0], memo)
        return PrintStat(parent=self.parent, expr=new_expr, symtab=self.symtab)


class PrintCommand(Stat):  # low-level node
    def __init__(self, parent=None, src=None, print_type=None, symtab=None):
        log_indentation(bold(f"New PrintCommand Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
        self.src = src
        if src.alloct != 'reg':
            raise RuntimeError('Trying to print a symbol not stored in a register')

        self.print_type = print_type

    def used_variables(self):
        return [self.src]

    def human_repr(self):
        return f"{blue('print')} {self.src}"

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['src'], mapping, create_new=create_new)

    def __deepcopy__(self, memo):
        return PrintCommand(parent=self.parent, src=self.src, print_type=self.print_type, symtab=self.symtab)


class ReadStat(Stat):
    def __init__(self, parent=None, symtab=None):
        log_indentation(bold(f"New ReadStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)

    def lower(self):
        tmp = new_temporary(self.symtab, TYPENAMES['int'])
        read = ReadCommand(dest=tmp, symtab=self.symtab)
        stlist = StatList(children=[read], symtab=self.symtab)
        return self.parent.replace(self, stlist)

    def __deepcopy__(self, memo):
        return ReadStat(parent=self.parent, symtab=self.symtab)


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

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['dest'], mapping, create_new=create_new)

    def __deepcopy__(self, memo):
        return ReadCommand(parent=self.parent, dest=self.dest, symtab=self.symtab)


class ReturnStat(Stat):
    def __init__(self, parent=None, children=[], symtab=None):
        log_indentation(bold(f"New ReturnStat Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)
        for child in self.children:
            child.parent = self

    def type_checking(self, returns, function_returns):
        masks = []

        for i in range(len(returns)):
            if returns[i].stype.name == function_returns[i].stype.name:
                continue

            if returns[i].stype.is_numeric() and function_returns[i].stype.is_numeric():
                if returns[i].stype.size > function_returns[i].stype.size:
                    continue  # we can return, for example, a byte as an int

                masks += mask_numeric(returns[i], self.symtab)
                continue

            # check if we're returning a pointer when we were expecting an array, it's good since we only return references
            # TODO: check that we are not returning local references
            if returns[i].is_pointer() and function_returns[i].is_array() and (returns[i].stype.pointstotype.name == function_returns[i].stype.basetype.name):
                continue

            raise RuntimeError(f"Trying to return a value of type {returns[i].stype.name} instead of {function_returns[i].stype.name}")

        return masks

    def lower(self):
        stats = self.children

        function_definition = self.get_function()
        if function_definition == 'main':
            raise RuntimeError("The main function should not have return statements")

        # check that the function returns as many values as the defined ones
        if len(function_definition.returns) > len(self.children):
            raise RuntimeError(f"Too few values are being returned in function {function_definition.symbol.name}")
        elif len(function_definition.returns) < len(self.children):
            raise RuntimeError(f"Too many values are being returned in function {function_definition.symbol.name}")

        returns = [x.destination() for x in self.children]
        stats += self.type_checking(returns, function_definition.returns)

        stats.append(BranchStat(parent=self, target=None, parameters=function_definition.parameters, returns=returns, symtab=self.symtab))

        stat_list = StatList(self.parent, stats, self.symtab)
        return self.parent.replace(self, stat_list)

    def __deepcopy__(self, memo):
        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return ReturnStat(parent=self.parent, children=new_children, symtab=self.symtab)


class BranchStat(Stat):  # low-level node
    def __init__(self, parent=None, cond=None, target=None, negcond=False, parameters=[], returns=[], symtab=None):
        """cond == None -> branch always taken.
        If negcond is True and Cond != None, the branch is taken when cond is false,
        otherwise the branch is taken when cond is true.
        If the target is a function symbol, this is a branch-and-link instruction.
        If target is None, the branch is a return and the 'target' is computed at runtime"""
        log_indentation(bold(f"New BranchStat Node (id: {id(self)})"))
        super().__init__(parent, [], symtab)
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
        if isinstance(self.target, Symbol) and isinstance(self.target.stype, FunctionType):
            return True
        return False

    def human_repr(self):
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
                    new_temp = new_temporary(self.symtab, self.cond.stype)
                    mapping[self.cond] = new_temp
                    self.cond = new_temp

        if self.target and not self.is_call():
            if create_new:
                new_target = TYPENAMES['label']()
                mapping[self.target] = new_target
                self.target = new_target

    def __deepcopy__(self, memo):
        return BranchStat(parent=self.parent, cond=self.cond, target=self.target, negcond=self.negcond, symtab=self.symtab)


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
        new = EmptyStat(parent=self.parent, symtab=self.symtab)
        new.set_label(self.get_label())
        return new


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

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['dest', 'symbol'], mapping, create_new=create_new)

    def __deepcopy__(self, memo):
        return LoadPtrToSym(parent=self.parent, dest=self.dest, symbol=self.symbol, symtab=self.symtab)


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
        if self.dest.alloct == 'reg' and isinstance(self.dest.stype, PointerType):
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

    def human_repr(self):
        if isinstance(self.dest.stype, PointerType):
            return f"[{self.dest}] {bold('<-')} {self.symbol}"
        return f"{self.dest} {bold('<-')} {self.symbol}"

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['dest', 'symbol'], mapping, create_new=create_new)
        if self.killhint is not None and self.killhint.is_temporary and self.killhint in mapping:
            self.killhint = mapping[self.killhint]

    def __deepcopy__(self, memo):
        return StoreStat(parent=self.parent, dest=self.dest, symbol=self.symbol, killhint=self.killhint, symtab=self.symtab)


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

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['dest', 'symbol'], mapping, create_new=create_new)
        if self.usehint is not None and self.usehint.is_temporary and self.usehint in mapping:
            self.usehint = mapping[self.usehint]

    def __deepcopy__(self, memo):
        return LoadStat(parent=self.parent, dest=self.dest, symbol=self.symbol, usehint=self.usehint, symtab=self.symtab)


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

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['dest'], mapping, create_new=create_new)

    def __deepcopy__(self, memo):
        return LoadImmStat(parent=self.parent, dest=self.dest, val=self.val, symtab=self.symtab)


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

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['dest', 'srca', 'srcb'], mapping, create_new=create_new)

    def __deepcopy__(self, memo):
        return BinStat(parent=self.parent, dest=self.dest, op=self.op, srca=self.srca, srcb=self.srcb, symtab=self.symtab)


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

    def replace_temporaries(self, mapping, create_new=True):
        replace_temporary_attributes(self, ['dest', 'src'], mapping, create_new=create_new)

    def __deepcopy__(self, memo):
        return UnaryStat(parent=self.parent, dest=self.dest, op=self.op, src=self.src, symtab=self.symtab)


class StatList(Stat):  # low-level node
    def __init__(self, parent=None, children=None, flat=False, symtab=None):
        log_indentation(bold(f"New StatList Node (id: {id(self)})"))
        super().__init__(parent, children, symtab)
        # when printing, print line numbers of flattened StatLists
        self.flat = flat

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
        if isinstance(self.parent, StatList):
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
            self.flat = True

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
            raise RuntimeError(f"Can't find instruction '{instruction}' to remove in StatList {id(self)}")

    def replace_temporaries(self, mapping, create_new=True):
        for child in self.children:
            child.replace_temporaries(mapping, create_new)

    def __deepcopy__(self, memo):
        new_children = []
        for child in self.children:
            new_children.append(deepcopy(child, memo))

        return StatList(parent=self.parent, children=new_children, flat=self.flat, symtab=self.symtab)


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

    def replace_temporaries(self, mapping, create_new=True):
        pass

    def __deepcopy__(self, memo):
        new_body = deepcopy(self.body, memo)
        new_defs = deepcopy(self.defs, memo)

        return Block(parent=self.parent, gl_sym=self.global_symtab, lc_sym=self.local_symtab, defs=new_defs, body=new_body)


# DEFINITIONS

class Definition(IRNode):
    def __init__(self, parent=None, symbol=None):
        super().__init__(parent, [], None)
        self.parent = parent
        self.symbol = symbol


class FunctionDef(Definition):
    def __init__(self, parent=None, symbol=None, parameters=[], body=None, returns=[], called_by_counter=0):
        log_indentation(bold(f"New Functions Definition Node (id: {id(self)})"))
        super().__init__(parent, symbol)
        self.body = body
        self.body.parent = self
        self.parameters = parameters
        self.returns = returns
        self.called_by_counter = called_by_counter

    def get_global_symbols(self):
        return self.body.global_symtab.exclude([TYPENAMES['function'], TYPENAMES['label']])

    def __deepcopy__(self, memo):
        new_body = deepcopy(self.body, memo)

        return FunctionDef(parent=self.parent, symbol=self.symbol, parameters=self.parameters, body=new_body, returns=self.returns, called_by_counter=self.called_by_counter)


class DefinitionList(IRNode):
    def __init__(self, parent=None, children=None):
        log_indentation(bold(f"New Definition List Node (id: {id(self)})"))
        super().__init__(parent, children, None)

    def append(self, elem):
        elem.parent = self
        self.children.append(elem)

    def remove(self, elem):
        self.children.remove(elem)

    def __deepcopy__(self, memo):
        return DefinitionList(parent=self.parent, children=self.children)
