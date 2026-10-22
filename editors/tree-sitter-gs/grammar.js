// A tolerant lexical grammar for highlighting incomplete GS edits.
// Syntax and type diagnostics are provided by the actual GS compiler via LSP.
module.exports = grammar({
  name: 'gs',
  word: $ => $.identifier,
  extras: $ => [/\s/, $.comment],
  rules: {
    source_file: $ => repeat($._item),
    _item: $ => choice($.identifier, $.keyword, $.string, $.number, $.operator, $.delimiter, $.block, $.parenthesized, $.indexed),
    block: $ => seq('{', repeat($._item), '}'),
    parenthesized: $ => seq('(', repeat($._item), ')'),
    indexed: $ => seq('[', repeat($._item), ']'),
    identifier: $ => /[A-Za-z_$][A-Za-z0-9_$]*/,
    keyword: $ => choice('func','type','struct','interface','enum','extends','implements','constructor','super','override','static','public','private','protected','readonly','var','const','return','if','else','for','range','switch','case','default','break','continue','async','await','new','export','import','from','as','true','false','nil','undefined','int','float','float64','number','string','bool','any','unknown','never','void','try','catch','throw','typeof','instanceof'),
    string: $ => token(choice(/"([^"\\\n]|\\.)*"/, /'([^'\\\n]|\\.)*'/)),
    number: $ => /[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?/,
    comment: $ => token(choice(/\/\/[^\n]*/, /\/\*[^*]*\*+([^/*][^*]*\*+)*\//)),
    operator: $ => token(choice('...', '?.', '??', ':=', '==', '!=', '<=', '>=', '&&', '||', '++', '--', '+=', '-=', /[=+*\/%!<>?|&-]/)),
    delimiter: $ => /[.,:;]/,
  }
});
