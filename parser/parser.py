from lark import Lark, Transformer
from pathlib import Path

grammar_path = Path(__file__).parent / "new_grammar.lark"
with open(grammar_path, "r", encoding="utf-8") as f:
  grammar = f.read()

parser = Lark(grammar, start="start", parser="lalr")

def parse_code(code: str):
  return parser.parse(code)