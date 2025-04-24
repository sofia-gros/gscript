from lark import Transformer, Tree

class MyLangTransformer(Transformer):
    def start(self, items):
        return "\n".join(str(item) for item in items)

    def import_stmt(self, items):
        path = items[0].value.strip('"')
        return f'import * as {path} from "{path}";'

    def func_def(self, items):
        name = items[0]
        if isinstance(items[1], list):
            args = items[1]
            return_type = str(items[2])
            body = items[3]
        else:
            args = []
            return_type = str(items[1])
            body = items[2]
        arg_list = ", ".join(args)
        return f"function {name}({arg_list}) {body}"

    def param(self, items):
        return str(items[0])

    def block(self, items):
        inner = "\n  ".join(items) if items else ""
        return "{\n  " + inner + "\n}"

    def return_stmt(self, items):
        return f"return {items[0]};"

    def var_decl_stmt(self, items):
        kind = str(items[0])
        name = str(items[1])
        value = items[3]
        return f"{kind} {name} = {value};"

    def assign_stmt(self, items):
        return f"{items[0]} = {items[1]};"

    def expr_stmt(self, items):
        return f"{items[0]};"

    def add(self, items):
        return f"{items[0]} + {items[1]}"

    def sub(self, items):
        return f"{items[0]} - {items[1]}"

    def mul(self, items):
        return f"{items[0]} * {items[1]}"

    def div(self, items):
        return f"{items[0]} / {items[1]}"

    def number(self, items):
        return str(items[0])

    def string(self, items):
        return items[0].value

    def var(self, items):
        return str(items[0])

    def func_call(self, items):
        name = str(items[0])
        args = items[1:] if len(items) > 1 else []
        args_code = ", ".join(str(arg) for arg in args[0].children) if args else ""
        if name == "print":
            return f"console.log({args_code})"
        return f"{name}({args_code})"

    def arguments(self, items):
        return items
    
    def self_member(self, items):
        return f"this.{items[1]}"