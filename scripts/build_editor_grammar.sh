#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../editors/tree-sitter-gs"
tree-sitter generate
git diff --exit-code src
tree-sitter test
tree-sitter parse ../../examples/advanced/main.gs
tree-sitter query ../zed/languages/gs/highlights.scm ../../examples/advanced/main.gs
tree-sitter query ../zed/languages/gs/brackets.scm ../../examples/advanced/main.gs
tree-sitter query ../zed/languages/gs/indents.scm ../../examples/advanced/main.gs
mkdir -p ../zed/grammars
tree-sitter build --wasm --output gs.wasm
tree-sitter parse --wasm ../../examples/advanced/main.gs
mv gs.wasm ../zed/grammars/gs.wasm
