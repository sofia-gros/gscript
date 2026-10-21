# GS 0.4 release contract

The existing GS syntax is sufficient: imports, constructors, property access and type annotations are extended semantically to external module types. No new syntax is required.

The agreed scope adds TypeScript-backed checking of imported JS/TS and installed node_modules using declarations, JSDoc and inferred types; local dependency emission in all three formats; content-validated caching; and iterative GS module loading. Unannotated dynamic JavaScript and explicit any retain their JavaScript semantics. Dependencies and browser bundling remain project-managed.

Release requires passing the complete GS regression suite, real Phaser declarations and invalid API tests, JS/MJS execution, strict TS compilation and execution, cache invalidation tests, deep module loading, packaged compiler smoke tests, browser scene startup, and the existing supported Python/Node/OS release matrix. No known failure in these promised features is accepted for release.

See interop.md for the final user-facing behavior and measured performance. v0.3's contract remains historical; this contract supersedes its external-import-as-any boundary for project compilation.

## Language proposal F01–F13

The release also includes the language extension proposal. Final syntax and semantics are fixed in language-v0.4-extensions.md. GS performs its own compatibility, inheritance, visibility, generic, nullable and exhaustiveness checks in Python. TypeScript is a declaration reader and an independent consumer of emitted TS, never the GS semantic checker. Every feature requires valid/invalid native checks and execution of JS/MJS and strict TS output. Tests explicitly forbid spawning TypeScript during GS-only checks and ensure invalid external calls fail before output processing.
