(comment) @comment
(string) @string
(number) @number
(keyword) @keyword
(identifier) @variable
(operator) @operator
(delimiter) @punctuation.delimiter
["{" "}" "[" "]" "(" ")"] @punctuation.bracket

((identifier) @function.builtin
  (#match? @function.builtin "^(print|println|printf|len|panic)$"))
