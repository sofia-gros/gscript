# GS 0.3 release contract

This document fixes the implementation scope before the compiler release.

## Language decision

GS keeps its Go-inspired declarations, functions, structs, receiver methods,
arrays, control flow and static checks, together with JavaScript objects,
modules and async/await. `.gs` is the primary source extension; `.gos` remains
accepted. No unrelated syntax expansion is needed to deliver this compiler.
Local modules must share types and validate their imports, rather than silently
turning GS code into `any`. External JavaScript APIs keep an explicit dynamic
boundary; the compiler cannot prove behavior of code it does not compile.

## Release gates

- Syntax errors, undefined names and incompatible types fail compilation.
- Local module exports and types are checked, including aliases and cycles.
- `--format js|mjs|ts` controls output and local import specifiers.
- JS/MJS are ES2022 modules. JS project output declares its module mode.
- TS output preserves usable types and compiles to executable JS with TypeScript.
- Every supported output is tested by the tool that consumes it, not only by
  string comparisons: Node for JS/MJS, TypeScript then Node for TS.
- Invalid input never replaces successful output.
- Compiler distributions are installed or started outside the source tree and tested.
- Release automation runs the tests and only publishes after all required jobs pass.
- README commands, language specification, version, artifact names and release
  notes must match the implementation.

No release is permitted with a failing gate or a known bug in the promised
behavior. Passing these gates is evidence, not a mathematical proof of zero bugs.
Changing an extension does not supply APIs absent from a browser or Node runtime.

Go runtime compatibility (goroutines, channels, Go's standard library and memory
model) is not part of the agreed JavaScript-based GS language. A request for full
Go compatibility is a different language/runtime contract and must be resolved
before claiming compatibility.
