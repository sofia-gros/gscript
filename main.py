from parser.parser import parse_code
from parser.new_transformer import MyLangTransformer
from pathlib import Path

if __name__ == "__main__":
  directory_path = Path(__file__).parent
  code_path = directory_path.joinpath("examples/main.gos")
  code = code_path.read_text(encoding="utf-8")

  tree = parse_code(code)

  transformer = MyLangTransformer()
  js_code = transformer.transform(tree)

  print("===== JavaScriptコード =====")
  print(js_code)