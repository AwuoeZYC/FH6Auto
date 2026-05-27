import os
import sys
import time
import subprocess

def main():
    # 参数接收格式：updater.exe <主程序PID> <旧EXE绝对路径> <新TMP绝对路径>
    if len(sys.argv) != 4:
        sys.exit(1)

    main_pid = sys.argv[1]
    old_exe = sys.argv[2]
    new_tmp = sys.argv[3]

    # 1. 循环等待主程序彻底自杀退出 (最多等10秒，防止文件占用)
    for _ in range(10):
        try:
            # 使用 tasklist 检查指定 PID 是否还存在
            output = subprocess.check_output(f'tasklist /FI "PID eq {main_pid}"', shell=True, text=True)
            if str(main_pid) not in output:
                break
        except Exception:
            pass
        time.sleep(1)

    time.sleep(0.5)  # 额外缓冲，确保 Windows 彻底释放文件句柄

    # 2. 删除旧版 EXE
    try:
        if os.path.exists(old_exe):
            os.remove(old_exe)
    except Exception:
        sys.exit(1)

    # 3. 将新下载的 TMP 临时文件重命名为正式 EXE
    try:
        if os.path.exists(new_tmp):
            os.rename(new_tmp, old_exe)
        else:
            sys.exit(1)
    except Exception:
        sys.exit(1)

    # 4. 重新拉起更新后的主程序，然后自己功成身退
    try:
        subprocess.Popen([old_exe])
    except Exception:
        pass
    
    sys.exit(0)

if __name__ == "__main__":
    main()