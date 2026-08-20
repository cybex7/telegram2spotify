#!/usr/bin/env python3
"""Dependency-free test runner (no pytest on this machine).

Collects test_* callables from the given modules, runs them, prints failures.
Kept pytest-compatible: `pytest tests/` works too once pytest is installed.
"""
import importlib.util, os, sys, traceback

HERE = os.path.dirname(os.path.abspath(__file__))

def load(path):
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def main(argv):
    files = argv or sorted(
        os.path.join(HERE, f) for f in os.listdir(HERE)
        if f.startswith("test_") and f.endswith(".py"))
    passed, failures = 0, []
    for path in files:
        mod = load(path)
        for name in sorted(n for n in dir(mod) if n.startswith("test_")):
            fn = getattr(mod, name)
            if not callable(fn):
                continue
            try:
                fn(); passed += 1
            except Exception:
                failures.append((os.path.basename(path), name, traceback.format_exc()))
    for f, name, tb in failures:
        print(f"\n{'='*70}\nFAIL {f}::{name}\n{'-'*70}\n{tb.rstrip()}")
    total = passed + len(failures)
    print(f"\n{passed}/{total} passed, {len(failures)} failed")
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
