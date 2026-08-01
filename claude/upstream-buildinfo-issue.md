# DRAFT upstream issue — build_info() silently truncates vendor-specific lists

**Status: draft for Tobi to review/file against zephyrproject-rtos/zephyr
(2026-07-23). Found while recording downstream rig-build provenance under
`cmake.vendor-specific.*`; workaround in btr-shields cmake/rig.cmake
(pre-`list(JOIN)`), pinned by test_tier2_build_info_rig_provenance.**

---

Title: cmake: build_info(): vendor-specific entries silently truncate
multi-element lists to their first element

## Describe the bug

`build_info()` (cmake/modules/extensions.cmake) writes vendor-specific
entries with a hardcoded `VALUE` type:

```cmake
if(ARGV0 STREQUAL "vendor-specific")
  set(type VALUE)
else()
  ...
  yaml_get(type NAME build_info_schema KEY properties cmake ${schema_check} type)
  if(type MATCHES "array")
    set(type LIST)
  ...
```

For schema-known keys the value type is derived from build-schema.yaml
(`array` → `LIST`), but the vendor-specific escape hatch — the only place
downstream modules may legally write (the schema's `cmake` object is
`additionalProperties: false`) — never gets `LIST`. Passing a
multi-element CMake list therefore silently records only the first
element in build_info.yml: no error, no warning, data loss.

## To Reproduce

```cmake
set(my_list "alpha;beta;gamma")
build_info(vendor-specific myns my-key VALUE ${my_list})
```

build_info.yml then contains:

```yaml
cmake:
  vendor-specific:
    myns:
      my-key: alpha        # beta, gamma silently dropped
```

## Expected behavior

Either (a) vendor-specific values support lists — e.g. detect
multi-element input and use `LIST` (matching how schema'd `array` keys
behave), or (b) multi-element input to a `VALUE`-typed entry is a
`FATAL_ERROR`/warning instead of silent truncation.

## Impact / workaround

Any downstream module recording list-shaped provenance (file lists,
component lists) under vendor-specific loses all but the first element
unless it pre-joins: `list(JOIN my_list ", " joined)` and records the
joined string. That works but is lossy-in-type (a string, not a YAML
sequence) and easy to miss precisely because the failure is silent.

## Environment

- Zephyr: main (observed at extensions.cmake:4046-4047 as of 2026-07)
- Host: any (pure CMake/yaml_set behavior)
