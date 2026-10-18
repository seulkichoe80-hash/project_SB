"""Reproducible static callsite inventory; does not open application databases."""
import ast
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]


def inventory():
    result=[]
    for file in sorted((ROOT/'apps/api').rglob('*.py')):
        tree=ast.parse(file.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ('execute','executemany','executescript','connect','transaction','backup'):
                result.append({'file':file.relative_to(ROOT).as_posix(),'line':node.lineno,'operation':node.func.attr,
                               'receiver':ast.unparse(node.func.value),
                               'sql_literal':node.args[0].value if node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str) else None})
    return {'scope':'All matching Python AST calls under apps/api; includes non-SQL execute/HTTP connect false positives, dynamic SQL callsites retained.',
            'calls':sorted(result,key=lambda r:(r['file'],r['line']))}


if __name__=='__main__':print(json.dumps(inventory(),ensure_ascii=False,indent=2))
