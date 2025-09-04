#!/usr/bin/env python3

"""Creates a Function Tree, a tree structure that shows the relations between
all the functions in the program; this is easier to traverse in respect to
the full IR tree

This tree can only be accessed via the static class FunctionTree"""

from logger import magenta, cyan


class FunctionNode:
    def __init__(self, symbol, children, parent=None, siblings=[]):
        self.symbol = symbol
        self.children = children
        self.parent = parent
        self.siblings = []

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
        function_tree = FunctionNode(symbol, [])
        for function in root.defs.children:
            new_node = FunctionTree.create_function_tree(function.body, function.symbol)
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
