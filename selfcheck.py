#!/usr/bin/env python3
"""Headless self-check for superengine (no cordis, no HMR, no three-repo import).

``superengine.cli.boot --report`` boots the cordis assembly, which is not
headless-safe in this environment (cordis' HMR import fails on the installed
watchdog).  This check therefore exercises the engine-free contract layer that
assembly itself relies on:

* semantic-version parsing and compatibility-interval arithmetic,
* the assembly-time provider gate: version range + runtime-checkable Protocol
  structure, with explicit rejection of incompatible / unknown providers,
* registry consistency (every declared contract has a version and a Protocol).

Run from the project root:

    python selfcheck.py

Prints ``selfcheck ok: ...`` and returns 0 on success, ``FAIL: ...`` and 1
on failure.
"""
from __future__ import annotations

from superengine import contracts as C
from superengine.contracts._version import format_version

CHECKS: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"{name}: {detail or 'condition is false'}")
    CHECKS.append(name)


def raises(fn, exc_type=Exception) -> bool:
    try:
        fn()
    except exc_type:
        return True
    except Exception:  # noqa: BLE001 - a different exception is still a failure
        return False
    return False


def check_versions() -> None:
    check("version.parse_two", C.parse_version("1.2") == (1, 2, 0))
    check("version.parse_padded", C.parse_version(" 2.0.3 ") == (2, 0, 3))
    check("version.format", format_version((1, 2, 3)) == "1.2.3")
    check("version.parse_interval",
          C.parse_interval(">=1.0,<2.0") == [(">=", (1, 0, 0)), ("<", (2, 0, 0))],
          C.parse_interval(">=1.0,<2.0"))
    check("version.in_range",
          C.version_in_interval("1.0.0", ">=1.0,<2.0")
          and C.version_in_interval("1.5.9", ">=1.0,<2.0")
          and not C.version_in_interval("2.0.0", ">=1.0,<2.0")
          and not C.version_in_interval("0.9.9", ">=1.0,<2.0"))
    check("version.pin",
          C.version_in_interval("1.2.0", "==1.2.0")
          and not C.version_in_interval("1.2.1", "==1.2.0"))
    check("version.lower_bound",
          C.version_in_interval("1.1.0", ">=1.1")
          and not C.version_in_interval("1.0.9", ">=1.1"))
    check("version.bad_version", raises(lambda: C.parse_version("one.two"),
                                        C.ContractVersionError))
    check("version.bad_interval", raises(lambda: C.parse_interval("banana"),
                                         C.ContractVersionError))
    check("version.empty_interval", raises(lambda: C.parse_interval(""),
                                           C.ContractVersionError))
    check("version.error_type", issubclass(C.ContractVersionError, ValueError))


class _WorldSpecProvider:
    """Minimal object satisfying the ``WorldSpecSource`` Protocol."""

    def generate(self, width: int, height: int, seed: int, **kw) -> dict:
        return {"width": width, "height": height, "seed": seed}

    def save(self, world, out_dir, *, tile_m: float, generator: str) -> dict:
        return {"world": world, "tile_m": tile_m, "generator": generator}

    def load(self, spec_dir, *, layers=None) -> dict:
        return {"dir": spec_dir, "layers": layers}

    def validate_spec(self, spec_dir) -> list:
        return []

    def meta(self, spec_dir) -> dict:
        return {}


def check_registry() -> None:
    check("registry.count", len(C.CONTRACT_VERSIONS) == 8, C.CONTRACT_VERSIONS)
    check("registry.protocols",
          set(C.CONTRACTS) == set(C.CONTRACT_VERSIONS),
          set(C.CONTRACTS) ^ set(C.CONTRACT_VERSIONS))
    versions = {name: C.parse_version(v) for name, v in C.CONTRACT_VERSIONS.items()}
    check("registry.all_1x",
          all(v >= (1, 0, 0) and v < (2, 0, 0) for v in versions.values()),
          versions)


def check_provider_gate() -> None:
    provider = _WorldSpecProvider()
    supported = {"worldspec_source": ">=1.0,<2.0"}

    check("gate.structure", isinstance(provider, C.WorldSpecSource))
    try:
        C.check_provider(provider, supported)  # must not raise
    except Exception as exc:  # noqa: BLE001 - a valid provider must pass
        raise AssertionError(f"gate.accept: {exc!r}") from exc
    CHECKS.append("gate.accept")
    check("gate.verify",
          C.verify_provider(provider, supported) == {"worldspec_source": "ok"},
          C.verify_provider(provider, supported))

    check("gate.reject_structure",
          raises(lambda: C.check_provider(object(), supported),
                 C.ContractVersionError))
    check("gate.reject_interval",
          raises(lambda: C.check_provider(provider,
                                          {"worldspec_source": ">=2.0"}),
                 C.ContractVersionError))
    check("gate.reject_unknown",
          raises(lambda: C.check_provider(provider, {"bogus": ">=1.0"}),
                 C.ContractVersionError))
    check("gate.compat_ok",
          C.check_compat("worldspec_source", "1.0.0", supported) is None)
    check("gate.compat_bad",
          raises(lambda: C.check_compat("worldspec_source", "2.0.0", supported),
                 C.ContractVersionError))
    check("gate.check_all",
          C.check_all(C.CONTRACT_VERSIONS, supported) is None
          and raises(lambda: C.check_all(C.CONTRACT_VERSIONS,
                                         {"worldspec_source": "<1.0"}),
                     C.ContractVersionError))


def run() -> None:
    check_versions()
    check_registry()
    check_provider_gate()


def main() -> int:
    try:
        run()
    except Exception as exc:  # noqa: BLE001 - self-check must report, not traceback
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1
    print(f"selfcheck ok: superengine contract layer "
          f"({len(CHECKS)} checks: versions/registry/provider-gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
