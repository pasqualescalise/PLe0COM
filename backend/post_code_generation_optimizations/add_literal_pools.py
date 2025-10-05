#!/usr/bin/env python3

"""
Sometimes functions are long, and sometimes functions are longer than 510 instructions.

In ARM, values are loaded using offsets relative to the PC, and the maximum offset is 510;
to solve this, every 510 instructions we add a pool, a place for the assembler to put
this offset. In practice, this means adding snippets like

```
b lxxx
    .ltorg
lxxx:
```

where .ltorg allocates the pool and the unconditional branch makes the PC skip it

TODO: this could be improved by allocating the pool only if it is actually needed,
      for example only if we actually try to load a far away address
"""

from ir.ir import TYPENAMES
from backend.codegenhelp import ASMInstruction
from logger import green, magenta


def add_literal_pools(code):
    count = 0
    indexes = []
    for i in range(len(code)):
        if code[i].instruction == ".ltorg":  # .ltorg is already added at the end of every function
            count = 0
            continue
        count += 1
        if count > 510:
            # account for the sliding when inserting the new instructions
            indexes.append(i + len(indexes))
            count = 0

    for i in indexes:
        new_label_name = magenta(TYPENAMES['label']().name)
        branch = ASMInstruction('b', args=[new_label_name])
        code.insert(i, branch)
        pool = ASMInstruction('.ltorg', comment="constant pool")
        code.insert(i + 1, pool)
        label = ASMInstruction(f"{new_label_name}:", indentation=1)
        code.insert(i + 2, label)

    print(green(f"Added {len(indexes)} constant pool{'s' if len(indexes) == 0 or len(indexes) > 1 else ''}"))

    return code
