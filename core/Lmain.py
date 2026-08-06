# core/Lmain.py
import os, json, uuid, hashlib, zipfile, subprocess, glob, re
from pathlib import Path

def scan_versions(game_root):
    root = Path(game_root) / "versions"
    out = []
    if not root.exists():
        return out
    for d in root.iterdir():
        if not d.is_dir() or d.name == "natives":
            continue
        js = [f for f in os.listdir(d) if f.endswith(".json")]
        if len(js) != 1:
            continue
        out.append({"folder_name": d.name, "json_name": js[0], "json_path": str(d / js[0])})
    return out

def find_java_installations():
    found = []
    jh = os.environ.get("JAVA_HOME")
    if jh:
        exe = os.path.join(jh, "bin", "java.exe")
        if os.path.exists(exe):
            found.append(exe)
    for base in [
        r"C:\Program Files\Java",
        r"C:\Program Files (x86)\Java",
        r"C:\Program Files\Zulu",
        r"C:\Program Files\Eclipse Adoptium",
        r"C:\Program Files\Microsoft\jdk-*",
        r"C:\Program Files\BellSoft",
        r"C:\Program Files\Amazon Corretto",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Java"),
    ]:
        if not base:
            continue
        if "*" in base:
            for m in glob.glob(base):
                if os.path.isdir(m):
                    exe = os.path.join(m, "bin", "java.exe")
                    if os.path.exists(exe):
                        found.append(exe)
        elif os.path.isdir(base):
            for root, _, files in os.walk(base):
                if "java.exe" in files:
                    found.append(os.path.join(root, "java.exe"))
    return list(dict.fromkeys(found))

def detect_java_version(java_path):
    try:
        r = subprocess.run([java_path, "-version"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            lines = r.stderr.strip().split("\n")
            return lines[0] if lines else "Unknown"
        return "Unknown"
    except:
        return "Error"

def detect_java_major(java_path):
    ver = detect_java_version(java_path)
    m = re.search(r'"(\d+)', ver)
    return int(m.group(1)) if m else 0

def offline_account(name):
    raw = bytearray(hashlib.md5(("OfflinePlayer:" + name).encode()).digest())
    raw[6] = (raw[6] & 0x0f) | 0x30
    raw[8] = (raw[8] & 0x3f) | 0x80
    uid = str(uuid.UUID(bytes=bytes(raw))).replace("-", "")
    return {
        "name": name,
        "uuid": uid,
        "accessToken": str(uuid.uuid4()),
        "clientToken": str(uuid.uuid4()),
        "authType": "offline",
        "userType": "offline"
    }

def get_version_type(json_path, folder_name=""):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    mc = data.get("mainClass", "")
    if "BootstrapLauncher" in mc:
        return "forge"
    if "KnotClient" in mc:
        if "quilt" in folder_name.lower():
            return "quilt"
        return "fabric"
    return "vanilla"

def get_java_requirement(json_path):
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        major = data.get("javaVersion", {}).get("majorVersion")
        if major:
            return int(major)
        ver = data.get("id", "")
        if not ver:
            return None
        parts = ver.split(".")
        nums = [int(p) for p in parts[:2]]
        if nums[0] == 1:
            if nums[1] >= 20:
                return 21
            if nums[1] >= 18:
                return 17
            if nums[1] >= 17:
                return 16
            if nums[1] >= 12:
                return 8
        elif nums[0] >= 21:
            return 21
    except:
        pass
    return None

def pick_java(java_path, json_path):
    need = get_java_requirement(json_path)
    if not need:
        return java_path, detect_java_version(java_path) if java_path else "Unknown"
    if java_path and os.path.exists(java_path):
        if detect_java_major(java_path) >= need:
            return java_path, detect_java_version(java_path)
    for p in find_java_installations():
        if detect_java_major(p) >= need:
            return p, detect_java_version(p)
    return java_path, detect_java_version(java_path) if java_path else "Unknown"

def verify_libraries(lib_paths):
    missing = []
    for p in lib_paths:
        if not os.path.exists(p):
            missing.append(p)
    return missing

def check_assets(game_root, asset_id):
    idx_path = os.path.join(game_root, "assets", "indexes", f"{asset_id}.json")
    if not os.path.exists(idx_path):
        return False, "索引不存在"
    try:
        with open(idx_path, encoding="utf-8") as f:
            idx = json.load(f)
        objs = idx.get("objects", {})
        if not objs:
            return False, "索引为空"
        obj_dir = os.path.join(game_root, "assets", "objects")
        missing = 0
        for _, meta in objs.items():
            h = meta.get("hash", "")
            if not h:
                continue
            if not os.path.exists(os.path.join(obj_dir, h[:2], h)):
                missing += 1
        if missing:
            return False, f"缺少 {missing} 个资源"
        return True, "资源完整"
    except Exception as e:
        return False, str(e)

def unpack_natives(native_list, target_dir):
    for p in native_list:
        if os.path.exists(p):
            with zipfile.ZipFile(p, "r") as z:
                z.extractall(target_dir)

def resolve_libraries(libs, game_root, ver_type):
    cp, natives = [], []
    for lib in libs:
        if "downloads" in lib:
            if "artifact" in lib["downloads"]:
                cp.append(os.path.join(game_root, "libraries", lib["downloads"]["artifact"]["path"]))
            if "classifiers" in lib["downloads"]:
                for name, info in lib["downloads"]["classifiers"].items():
                    if "natives" in name.lower():
                        natives.append(os.path.join(game_root, "libraries", info["path"]))
            continue

        if "name" not in lib:
            continue

        parts = lib["name"].split(":")
        if len(parts) < 3:
            continue

        group, artifact, ver = parts[0], parts[1], parts[2]
        classifier = parts[3] if len(parts) >= 4 else None
        gpath = group.replace(".", os.sep)

        if ver_type in ("fabric", "quilt"):
            if classifier and "natives" in classifier.lower():
                natives.append(os.path.join(game_root, "libraries", gpath, artifact, ver, f"{artifact}-{ver}-{classifier}.jar"))
            else:
                cp.append(os.path.join(game_root, "libraries", gpath, artifact, ver, f"{artifact}-{ver}.jar"))
        else:
            #这不是冗余代码，不要乱动，动了后果自负(ᗜ ˰ ᗜ) 
            if "downloads" in lib:
                continue
            if classifier and "natives" in classifier.lower():
                natives.append(os.path.join(game_root, "libraries", gpath, artifact, ver, f"{artifact}-{ver}-{classifier}.jar"))
            else:
                cp.append(os.path.join(game_root, "libraries", gpath, artifact, ver, f"{artifact}-{ver}.jar"))
    return cp, natives

def build_jvm_args(base, extra, cp):
    merged = base + extra
    cleaned = []
    i = 0
    while i < len(merged):
        arg = merged[i]
        if arg in ("-cp", "-classpath", "--module-path"):
            i += 2
            continue
        cleaned.append(arg)
        i += 1
    cleaned.extend(["-cp", cp])
    return cleaned

def build_game_args(raw_args):
    return raw_args

def parse_version(game_root, ver_id, folder, json_name, ver_type):
    path = os.path.join(game_root, "versions", folder, json_name)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    real_id = raw.get("id", ver_id)
    cfg = {
        "id": real_id,
        "mainClass": raw["mainClass"],
        "assets_id": raw.get("assetIndex", {}).get("id", ""),
        "jar_path": os.path.join(game_root, "versions", real_id, f"{real_id}.jar"),
        "ver_type": ver_type
    }

    #大坑，1.17前后版本格式完全不一样，动之前看好了（当然最好别动）
    if "arguments" in raw:
        cfg["raw_args"] = [a for a in raw["arguments"]["game"] if isinstance(a, str)]
        cfg["jvm_args"] = [a for a in raw.get("arguments", {}).get("jvm", []) if isinstance(a, str)]
    else:
        args = raw.get("minecraftArguments", "")
        cfg["raw_args"] = args.split(" ") if args else []
        cfg["jvm_args"] = []

    libs, natives = resolve_libraries(raw["libraries"], game_root, ver_type)
    cfg["libraries"] = libs
    cfg["natives"] = natives
    return cfg

def launch_version(game_root, java_path, version_info, mem_min=1024, mem_max=4096,
                   player_name="Player", extra_args=None):
    folder = version_info["folder_name"]
    json_name = version_info["json_name"]
    json_path = version_info["json_path"]
    base_ver = folder.split("-")[0]
    ver_type = get_version_type(json_path, folder)

    java_path, _ = pick_java(java_path, json_path)
    account = offline_account(player_name)
    cfg = parse_version(game_root, base_ver, folder, json_name, ver_type)

    all_libs = cfg["libraries"] + [cfg["jar_path"]]
    missing = verify_libraries(all_libs)
    if missing:
        print("[错误] 以下库文件缺失，无法启动:")
        for m in missing[:10]:
            print(f"  {m}")
        if len(missing) > 10:
            print(f"  ... 还有 {len(missing)-10} 个")
        print("请先下载完整游戏版本")
        return None

    if cfg.get("assets_id"):
        ok, msg = check_assets(game_root, cfg["assets_id"])
        if not ok:
            print(f"[警告] {msg}")

    natives_dir = os.path.join(game_root, "versions", "natives")
    os.makedirs(natives_dir, exist_ok=True)
    unpack_natives(cfg["natives"], natives_dir)

    cp = os.pathsep.join(cfg["libraries"] + [cfg["jar_path"]])
    env = os.environ.copy()
    env["PATH"] = natives_dir + os.pathsep + env["PATH"]

    base_jvm = [
        f"-Xms{mem_min}M", f"-Xmx{mem_max}M",
        f"-Djava.library.path={natives_dir}",
        "-Djava.net.preferIPv6Addresses=false",
        "-Djava.net.preferIPv4Stack=true",
        "-Dminecraft.launcher.brand=MCOpen",
        "-Dminecraft.launcher.version=1.0.0",
        "-Daccessibility.screen_reader=false",
        "-Dawt.accessibility=false",
        "-Djavax.accessibility.assistive_technologies=",
        "--add-opens", "java.base/java.lang=ALL-UNNAMED",
        "--add-opens", "java.base/java.lang.invoke=ALL-UNNAMED",
        "--add-opens", "java.base/java.util=ALL-UNNAMED",
        "--add-opens", "java.base/java.io=ALL-UNNAMED",
        "--add-opens", "java.base/java.lang.reflect=ALL-UNNAMED",
    ]

    def subst(arg):
        for k, v in {
            "${natives_directory}": natives_dir,
            "${library_directory}": os.path.join(game_root, "libraries"),
            "${classpath_separator}": os.pathsep,
            "${game_directory}": game_root,
            "${assets_root}": os.path.join(game_root, "assets"),
            "${assets_index_name}": cfg["assets_id"],
            "${version_name}": cfg["id"],
            "${auth_player_name}": account["name"],
            "${auth_uuid}": account["uuid"],
            "${auth_access_token}": account["accessToken"],
            "${auth_session}": account["accessToken"],
            "${user_type}": account["authType"],
            "${user_properties}": "{}",
        }.items():
            arg = arg.replace(k, v)
        return arg

    extra_jvm = [subst(a) for a in cfg.get("jvm_args", [])]
    final_jvm = build_jvm_args(base_jvm, extra_jvm, cp)

    game_args = [subst(a) for a in cfg["raw_args"]]
    final_game = build_game_args(game_args)
    if extra_args:
        final_game += list(extra_args)

    cmd = [java_path] + final_jvm + [cfg["mainClass"]] + final_game
    return subprocess.Popen(cmd, cwd=game_root, env=env)