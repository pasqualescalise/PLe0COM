#!/usr/bin/env python3

"""Support functions for visiting the AST and the IR tree (which are
the same thing in this compiler).
These functions expose high level interfaces (passes) for actions that can be
applied to multiple IR nodes."""


def print_statement_list(node):
    """Navigation action: printing
    (only for StatList nodes the content is printed)"""
    try:
        node.print_content()
    except AttributeError as e:
         pass # not a StatList

def get_node_list(root, quiet=False):
    """Get a list of all nodes in the AST"""

    def register_nodes(l):
        def r(node):
            if node not in l:
                l.append(node)

        return r

    node_list = []
    root.navigate(register_nodes(node_list), quiet)
    return node_list

def lowering(node):
    """Navigation action: lowering
    (all high level nodes can be lowered to lower-level representation)"""
    try:
        check = node.lower()
        print('Lowering', type(node), id(node))
        if not check:
            raise RuntimeError("Node " + repr(node) + " did not return anything after lowering")
    except AttributeError as e:
         print('Lowering not yet implemented for type ' + repr(type(node)))

def flattening(node):
    """Navigation action: flattening
    (only StatList nodes are actually flattened)"""
    try:
        node.flatten()
    except AttributeError as e:
         print('Flattening not yet implemented for type ' + repr(type(node)))

def dotty_wrapper(fout):
    """Main function for graphviz dot output generation"""

    def dotty_function(irnode):
        from ir import Stat
        attrs = {'body', 'cond', 'thenpart', 'elsepart', 'call', 'step', 'expr', 'target', 'defs'} & set(
            dir(irnode))

        res = repr(id(irnode)) + ' ['
        if isinstance(irnode, Stat):
            res += 'shape=box,'
        res += 'label="' + repr(type(irnode)) + ' ' + repr(id(irnode))
        try:
            res += ': ' + irnode.value
        except AttributeError:
            pass
        try:
            res += ': ' + irnode.name
        except AttributeError:
            pass
        try:
            res += ': ' + getattr(irnode, 'symbol').name
        except AttributeError:
            pass
        res += '" ];\n'

        if 'children' in dir(irnode) and len(irnode.children):
            for node in irnode.children:
                res += repr(id(irnode)) + ' -> ' + repr(id(node)) + ' [pos=' + repr(
                    irnode.children.index(node)) + '];\n'
                if type(node) == str:
                    res += repr(id(node)) + ' [label=' + node + '];\n'
        for d in attrs:
            node = getattr(irnode, d)
            if d == 'target':
                if irnode.target is None:
                    res += repr(id(irnode)) + ' -> ' + 'return;\n'
                else:
                    res += repr(id(irnode)) + ' -> ' + repr(id(node.value)) + ' [label=' + node.name + '];\n'
            else:
                res += repr(id(irnode)) + ' -> ' + repr(id(node)) + ';\n'
        fout.write(res)
        return res

    return dotty_function

def print_dotty(root, filename):
    """Print a graphviz dot representation to file"""
    fout = open(filename, "w")
    fout.write("digraph G {\n")
    node_list = get_node_list(root, quiet=True)
    dotty = dotty_wrapper(fout)
    for n in node_list:
        dotty(n)
    fout.write("}\n")
