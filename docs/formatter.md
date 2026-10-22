# Formatter

```sh
gs fmt
gs fmt main.gs
gs fmt . --check
```

2スペースで整形し、コメントと文字列を維持します。整形後に再解析し、元の構文木と意味が等しいことを確認してから書き込みます。二度の整形で同一結果となることを回帰テストします。構文エラーや意味差を検出した場合は書き換えません。--checkは変更が必要なら終了値1、整形済みなら0です。

LSPのdocumentFormattingも同じ実装を使います。VSCodeの「Format Document」、Zedのフォーマット操作から利用できます。
