#!/usr/bin/env python3

"""Creates a Function Tree, a tree structure that shows the relations between
all the functions in the program; this is easier to traverse in respect to
the full IR tree

This tree can only be accessed via the static class FunctionTree"""

from logger import log_indentation, magenta, cyan
import logger


class FunctionNode:
    def __init__(self, symbol, children, parent=None, siblings=[], definition=None):
        self.symbol = symbol
        self.children = children
        self.parent = parent
        self.siblings = []
        self.definition = definition

    def __repr__(self):
        res = f"{cyan('|')} {magenta(f'{self.symbol.name}')}\n"
        for function in self.children:
            rep = repr(function).split("\n")[:-1]
            res += "\n".join([f"{' ' * 4}{s}" for s in rep])
            res += "\n"

        return res

    def is_parent_of(self, function):
        return function in self.children

    def is_sibling_of(self, function):
        return function in self.siblings

    def is_child_of(self, function):
        return self.parent == function


# Returns a tuple (x, y) encoding the distance between two functions:
#   x -> can be positive or negative, distance in the vertical direction
#   y -> can only be 0 or positive, distance in the horizontal direction (siblings)
def get_distance_between_functions(function1, function2):
    if function1 is None:
        return (0, 0)

    if function1 == function2:
        return (0, 0)

    if function1.is_parent_of(function2):
        return (1, 0)

    if function1.is_child_of(function2):
        return (-1, 0)

    if function1.is_sibling_of(function2):
        return (0, 1)

    # measure the distance from the parent FunctionNode
    distance = get_distance_between_functions(function1.parent, function2)
    return (distance[0] - 1, distance[1])


# Static class used to create and access the Function Tree
class FunctionTree:
    root = FunctionNode(None, [])

    @staticmethod
    def populate_function_tree(program, symbol):
        FunctionTree.root = FunctionTree.create_function_tree(program, symbol)

    @staticmethod
    def create_function_tree(root, symbol):
        function_tree = FunctionNode(symbol, [], definition=root)
        for function in root.body.defs.children:
            new_node = FunctionTree.create_function_tree(function, function.symbol)
            function_tree.children.append(new_node)
            new_node.parent = function_tree
            new_node.siblings = function_tree.children
        return function_tree

    # returns the FunctionNode with the wanted symbol
    @staticmethod
    def get_function_node(symbol):
        return FunctionTree.__get_function_node(FunctionTree.root, symbol)

    @staticmethod
    def __get_function_node(function_node, symbol):
        if function_node.symbol == symbol:
            return function_node

        for child in function_node.children:
            x = FunctionTree.__get_function_node(child, symbol)
            if x is not None:
                return x

        return None

    @staticmethod
    # returns the FuncDef with the symbol specified, if it's reachable
    # raises a RuntimeError if it doesn't find it
    def get_function_definition(target_function_symbol):
        function_definition = FunctionTree.get_function_node(target_function_symbol).definition
        if function_definition is None:
            raise RuntimeError(f"Can't find function {target_function_symbol.name}")

        return function_definition

    @staticmethod
    def get_global_symbol(symbol_name):
        return FunctionTree.root.definition.body.symtab.find(FunctionTree.root.definition, symbol_name)

    @staticmethod
    def navigate(action, *args, quiet=False):
        FunctionTree.__navigate(FunctionTree.root, action, *args, quiet=quiet)

    @staticmethod
    def __navigate(root, action, *args, quiet=False):
        if not quiet:
            log_indentation(f"Navigating to function {magenta(root.symbol.name)}, {id(root.definition)}")
        logger.indentation += 1

        for child in root.children:
            FunctionTree.__navigate(child, action, *args, quiet=quiet)

        body = root.definition.body.body
        if not quiet:
            log_indentation(f"Navigating to {cyan(body.type_repr())}, {id(body)}")
        logger.indentation += 1

        for child in body.children:
            if 'navigate' in dir(child):
                if not quiet:
                    log_indentation(f"Navigating to child {cyan(child.type_repr())} of {cyan(body.type_repr())}, {id(body)}")
                logger.indentation += 1
                child.navigate(action, *args, quiet=quiet)
                logger.indentation -= 1
            else:
                if not quiet:
                    log_indentation(f"Performing action {magenta(action.__name__)} on child {cyan(child.type_repr())}, {id(child)}")
                action(child)

        logger.indentation -= 1
        if not quiet:
            log_indentation(f"Performing action {magenta(action.__name__)} on {cyan(body.type_repr())}, {id(body)}")

        action(body)
        logger.indentation -= 1
        if not quiet:
            log_indentation(f"Navigated function {magenta(root.symbol.name)}, {id(root.definition)}")
