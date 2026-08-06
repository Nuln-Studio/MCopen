#以命令行启动（不建议这样启动游戏，不方便而且有很多逻辑都是为了以后测试GUI方便）
import sys, os
from pathlib import Path
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)
from core.Lmain import scan_versions, launch_version

def pick_version(versions):
    print("\n可用游戏版本:")
    for i, v in enumerate(versions, 1):
        print(f"  {i}. {v['folder_name']}")
    print()
    while True:
        try:
            n = int(input("选择序号: "))
            if 1 <= n <= len(versions):
                return versions[n - 1]
            print("序号超出范围")
        except ValueError:
            print("请输入数字")

def main():
    game_root = os.path.join(PROJECT_ROOT, ".minecraft")
    versions = scan_versions(game_root)
    if not versions:
        fallback_root = os.path.join(os.path.dirname(__file__), ".minecraft")
        versions = scan_versions(fallback_root)
        if versions:
            game_root = fallback_root
            print(f"[调试]使用备选目录: {fallback_root}")

    java = r"C:\Program Files\Zulu\zulu-17\bin\java.exe"

    if not versions:
        print("没有找到任何版本")
        print(f"[调试]检查路径: {game_root} 或 {fallback_root}")
        return

    selected = pick_version(versions)
    print(f"\n启动 {selected['folder_name']} ...")

    proc = launch_version(game_root, java, selected, 2048, 4096, "Player")
    if proc:
        print(f"游戏已启动 (PID: {proc.pid})")
    else:
        print("启动失败")

if __name__ == "__main__":
    main()