

import argparse
import json
import sys
import urllib.error
import urllib.request

try:
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.version import InvalidVersion, Version
except ImportError:
    from pip._vendor.packaging.requirements import InvalidRequirement, Requirement
    from pip._vendor.packaging.specifiers import SpecifierSet
    from pip._vendor.packaging.version import InvalidVersion, Version


def fetch_pypi(name):
    url = f"https://pypi.org/pypi/{name}/json"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def pick_version(data, specifier):
    candidates = []
    for ver, files in data["releases"].items():
        if not files or all(f.get("yanked") for f in files):
            continue
        try:
            v = Version(ver)
        except InvalidVersion:
            continue
        if specifier.contains(v, prereleases=bool(specifier) and v.is_prerelease):
            candidates.append(v)
    return max(candidates) if candidates else None


def requires_python(data, version):
    for f in data["releases"].get(str(version), []):
        if f.get("requires_python"):
            return f["requires_python"]
    return None


def min_python(spec_str):
    lows = [
        Version(s.version.rstrip(".*"))
        for s in SpecifierSet(spec_str)
        if s.operator in (">=", ">", "~=", "==")
    ]
    return max(lows) if lows else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("--python", default="3.11")
    args = parser.parse_args()

    checked = 0
    not_found, incompatible, invalid = [], [], []
    highest = None  # (min_python, name, version, requires_python)

    with open(args.file) as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            try:
                req = Requirement(line)
            except InvalidRequirement:
                invalid.append(line)
                continue

            checked += 1
            data = fetch_pypi(req.name)
            if data is None:
                not_found.append(req.name)
                continue

            version = pick_version(data, req.specifier)
            if version is None:
                not_found.append(f"{req.name}{req.specifier} (no matching version)")
                continue

            rp = requires_python(data, version)
            if rp and not SpecifierSet(rp).contains(args.python):
                incompatible.append(f"{req.name}=={version} (requires {rp})")

            low = min_python(rp) if rp else None
            if low and (highest is None or low > highest[0]):
                highest = (low, req.name, version, rp)

    print(f"dependencies checked: {checked}")
    print(f"Not found on pypi: {', '.join(not_found) or 'none'}")
    print(f"incompatible with python {args.python}: {', '.join(incompatible) or 'none'}")
    if highest:
        print(f"highest requirement: {highest[1]} == {highest[2]} ({highest[3]})")
    else:
        print("highest requirement: none")
    if invalid:
        print(f"invalid lines skipped: {', '.join(invalid)}")


if __name__ == "__main__":
    sys.exit(main())
