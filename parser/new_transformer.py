# transformer.py
from lark import Transformer, Tree


def extract_param_names(tree):
    if tree.data == "params":
        return [child.children[0] for child in tree.children if isinstance(child, Tree) and child.data == "param"][0]
    return []

class MyLangTransformer(Transformer):
    def __init__(self):
        self.indent_level = 0
        self.indent_str = "  "  # 2スペース

    def _indent(self, line: str) -> str:
        return f"{self.indent_str * self.indent_level}{line}"

    def start(self, items):
        return "\n".join(items)

    def import_stmt(self, items):
        if len(items) == 2:
            return self._indent(f"import * as {items[0]} from {items[1]};")
        return self._indent(f"import * as {items[0]} from {items[0]};")

    def import_plain(self, items):  return str(items[0])
    def import_string(self, items): return str(items[0])

    def var_decl(self, items):
        kind, name = items[0], items[1]
        if len(items) == 4:
            expr = items[3].children[0] + " " if isinstance(items[3], Tree) else ""
        else: expr = ""
        value = items[-1]
        return self._indent(f"{kind} {name} = {expr}{value};")

    def class_member(self, items):
        return items[0]  # 文字列化された field_decl や func_def をそのまま返す

    def field_decl(self, items):
        name = items[0]
        value = items[2]
        return self._indent(f"{name} = {value};")

    def func_def(self, items):
        name = items[0]
        params = extract_param_names(items[1]) if isinstance(items[1], Tree) else ""
        body = items[-1]
        line = f"function {name}({params}) {body}"
        return self._indent(line)
        
    def async_func_def(self, items):
        name = items[0]
        params = extract_param_names(items[1]) if isinstance(items[1], Tree) else ""
        body = items[-1]
        line = f"async function {name}({params}) {body}"
        return self._indent(line)

    def return_stmt(self, items):
        return self._indent(f"return {items[0]};")

    def func_call_stmt(self, items):
        name = items[0]
        expr = items[1][0]
        if name == "printf": name = "console.log"
        return self._indent(f"{name}({expr});")

    def func_call(self, items):
        name = items[0]
        args = ", ".join(items[1]) if len(items) > 1 else ""
        return f"{name}({args})"

    def args(self, items): return items

    def block(self, items):
        out = ["{"]
        self.indent_level += 1
        for stmt in items:
            out.append(self._indent(stmt))
        self.indent_level -= 1
        out.append(self._indent("}"))
        return "\n".join(out)

    def class_def(self, items):
        name, body = items
        return self._indent(f"class {name} {body}")

    def class_method(self, items):
        name = items[0]
        params = extract_param_names(items[1]) if isinstance(items[1], Tree) else ""
        body = items[-1]
        line = f"{name}({params}) {body}"
        return self._indent(line)

    def class_block(self, items):
        out = ["{"]
        self.indent_level += 1
        for m in items:
            out.append(self._indent(m))
        self.indent_level -= 1
        out.append(self._indent("}"))
        return "\n".join(out)

    def if_stmt(self, items):
        cond, then_blk = items[0], items[1]
        if len(items) == 3:
            else_blk = items[2]
            return self._indent(f"if ({cond}) {then_blk} else {else_blk}")
        return self._indent(f"if ({cond}) {then_blk}")

    def for_stmt(self, items):
        # init: "let i = 0;"  cond, step, block
        init_raw = items[0].strip()
        if init_raw.endswith(";"):
            init_raw = init_raw[:-1]
        cond, step, blk = items[1], items[2], items[3]
        return self._indent(f"for ({init_raw}; {cond.strip("()")}; {step}) {blk}")

    def add(self, items): return f"({items[0]} + {items[1]})"
    def eq(self, items):  return f"({items[0]} == {items[1]})"
    def neq(self, items): return f"({items[0]} != {items[1]})"
    def gt(self, items):  return f"({items[0]} > {items[1]})"
    def lt(self, items):  return f"({items[0]} < {items[1]})"
    def gte(self, items): return f"({items[0]} >= {items[1]})"
    def lte(self, items): return f"({items[0]} <= {items[1]})"
    def assign(self, items): return f"{items[0]} = {items[1]}"
    def awa(self, items): return f"await {items[1]}"
    
    def attr_access(self, items):
        base, attr = str(items[0]), str(items[1])
        # self → this
        return f"this.{attr}" if base == "self" else f"{base}.{attr}"

    def var(self, items):    return str(items[0])
    def string(self, items): return str(items[0])
    def number(self, items): return str(items[0])

    def return_type(self, items): return ""  # 型情報は無視
    def empty_return(self, items): return ""