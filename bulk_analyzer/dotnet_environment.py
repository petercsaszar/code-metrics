import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from glob import glob

DOTNET_INSTALL_SCRIPT = os.getenv("DOTNET_INSTALL_SCRIPT", "/usr/local/bin/dotnet-install.sh")
DOTNET_INSTALL_DIR = os.getenv("DOTNET_INSTALL_DIR", "/usr/share/dotnet")
_NOOP = object()

_installed_sdks = None
_installed_workloads = None
_session_installed_workloads = set()


def _run_command(args):
    return subprocess.run(args, capture_output=True, text=True, check=True, encoding="utf-8", errors="replace")


def _parse_installed_sdks(raw_output):
    installed = []
    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            continue
        version = line.split()[0]
        installed.append(version)
    return installed


def _refresh_installed_sdks():
    global _installed_sdks
    try:
        result = _run_command(["dotnet", "--list-sdks"])
        _installed_sdks = _parse_installed_sdks(result.stdout)
    except FileNotFoundError:
        _installed_sdks = []
    except subprocess.CalledProcessError:
        _installed_sdks = []


def _ensure_installed_cache():
    if _installed_sdks is None:
        _refresh_installed_sdks()


def _is_version_installed(version):
    _ensure_installed_cache()
    if not _installed_sdks:
        return False
    version = version.strip()
    return any(sdk.startswith(version) for sdk in _installed_sdks)


def _install_dotnet(args):
    if not os.path.isfile(DOTNET_INSTALL_SCRIPT):
        print(f"⚠️ dotnet-install script not found at {DOTNET_INSTALL_SCRIPT}. Skipping automatic SDK installation.")
        return False

    install_args = [DOTNET_INSTALL_SCRIPT, "--install-dir", DOTNET_INSTALL_DIR, "--no-path"] + args
    try:
        subprocess.run(install_args, check=True)
        _refresh_installed_sdks()
        return True
    except subprocess.CalledProcessError as exc:
        print(f"❌ Failed to install .NET SDK ({' '.join(args)}): {exc}")
        return False


def _split_frameworks(raw):
    if not raw:
        return []
    return [item.strip() for item in raw.split(';') if item.strip()]


def _map_framework_to_channel(framework):
    if not framework:
        return None
    lowered = framework.lower().split('-')[0]
    if lowered.startswith("netstandard") or lowered.startswith("net4"):
        return None

    match = re.match(r"net(?:coreapp)?(?P<major>\d+)(?:\.(?P<minor>\d+))?", lowered)
    if not match:
        return None

    major = match.group("major")
    minor = match.group("minor") or "0"

    return f"{major}.{minor}"


def _collect_csproj_metadata(csproj_path):
    frameworks = set()
    workloads = set()
    try:
        tree = ET.parse(csproj_path)
        root = tree.getroot()
    except ET.ParseError:
        return frameworks, workloads

    for tf in root.findall(".//TargetFramework"):
        frameworks.update(_split_frameworks(tf.text))
    for tfs in root.findall(".//TargetFrameworks"):
        frameworks.update(_split_frameworks(tfs.text))

    workloads.update(_workloads_from_frameworks(frameworks))

    for elem in root.findall(".//UseMaui"):
        if _is_true(elem.text):
            workloads.add("maui")

    return frameworks, workloads


def _is_true(value):
    if value is None:
        return False
    return value.strip().lower() in {"true", "1", "yes"}


def _workloads_from_frameworks(frameworks):
    workloads = set()
    for framework in frameworks:
        lowered = (framework or "").lower()
        if "maui" in lowered:
            workloads.add("maui")
        if "android" in lowered:
            workloads.add("android")
        if "ios" in lowered:
            workloads.add("ios")
        if "maccatalyst" in lowered:
            workloads.add("maccatalyst")
        if "macos" in lowered:
            workloads.add("macos")
        if "tizen" in lowered:
            workloads.add("tizen")
        if "browser" in lowered or "wasm" in lowered:
            workloads.add("wasm-tools")
    return workloads


def _collect_sdk_requirements(repo_path):
    versions = set()
    channels = set()
    workloads = set()

    global_json = os.path.join(repo_path, "global.json")
    if os.path.isfile(global_json):
        try:
            with open(global_json, encoding="utf-8") as handle:
                data = json.load(handle)
            sdk_version = data.get("sdk", {}).get("version")
            if sdk_version:
                versions.add(str(sdk_version).strip())
            workloads.update(map(str, data.get("workloads", [])))
        except json.JSONDecodeError:
            print(f"⚠️ Could not parse global.json at {global_json}")

    for csproj in glob(os.path.join(repo_path, "**", "*.csproj"), recursive=True):
        frameworks, csproj_workloads = _collect_csproj_metadata(csproj)
        workloads.update(csproj_workloads)
        for framework in frameworks:
            channel = _map_framework_to_channel(framework)
            if channel:
                channels.add(channel)

    return versions, channels, workloads


def _refresh_installed_workloads():
    global _installed_workloads
    try:
        result = _run_command(["dotnet", "workload", "list", "--machine-readable"])
        try:
            data = json.loads(result.stdout or "{}")
            installed = {item.get("workloadId") for item in data.get("installed", []) if item.get("workloadId")}
            _installed_workloads = installed
        except json.JSONDecodeError:
            _installed_workloads = _parse_workload_list(result.stdout)
    except FileNotFoundError:
        _installed_workloads = set()
    except subprocess.CalledProcessError:
        try:
            result = _run_command(["dotnet", "workload", "list"])
            _installed_workloads = _parse_workload_list(result.stdout)
        except (FileNotFoundError, subprocess.CalledProcessError):
            _installed_workloads = set()


def _parse_workload_list(raw_output):
    workloads = set()
    capture = False
    for line in raw_output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if lowered.startswith("installed workloads"):
            capture = True
            continue
        if not capture:
            continue
        if ":" in stripped:
            continue
        token = stripped.split()[0]
        workloads.add(token)
    return workloads


def _ensure_workloads_cache():
    if _installed_workloads is None:
        _refresh_installed_workloads()


def _is_workload_installed(workload):
    _ensure_workloads_cache()
    if workload in _session_installed_workloads:
        return True
    return bool(_installed_workloads and workload in _installed_workloads)


def _install_workload(workload):
    if not workload:
        return False
    if _is_workload_installed(workload):
        return True
    print(f"⬇️ Installing .NET workload {workload}")
    try:
        subprocess.run(["dotnet", "workload", "install", workload, "--skip-manifest-update"], check=True)
        _session_installed_workloads.add(workload)
        _refresh_installed_workloads()
        return True
    except subprocess.CalledProcessError as exc:
        print(f"❌ Failed to install workload {workload}: {exc}")
        return False


def ensure_dotnet_environment(repo_path):
    versions, channels, workloads = _collect_sdk_requirements(repo_path)

    for version in sorted(versions):
        if _is_version_installed(version):
            continue
        print(f"⬇️ Installing .NET SDK {version} (from global.json)")
        _install_dotnet(["--version", version])

    for channel in sorted(channels):
        if _is_version_installed(channel):
            continue
        print(f"⬇️ Installing .NET SDK channel {channel} (from TargetFrameworks)")
        _install_dotnet(["--channel", channel])

    for workload in sorted(workloads):
        _install_workload(workload)