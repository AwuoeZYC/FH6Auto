import os
import sys
import threading
import webbrowser
import subprocess
import requests
import customtkinter as ctk
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import CURRENT_VERSION, get_asset_path, parse_version

class UpdaterWindow:
    """
    独立的热更新窗口模块。
    负责与 Github 通信、版本校验以及断点下载替换。
    """
    def __init__(self, parent_gui):
        self.parent = parent_gui
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("检查更新")
        self.window.geometry("340x220")
        self.window.resizable(False, False)
        self.window.transient(self.parent)

        # 居中显示
        self.window.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - 340) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - 220) // 2
        self.window.geometry(f"+{x}+{y}")
        
        self._setup_ui()
        
    def ui_call(self, func, *args, **kwargs):
        """线程安全 UI 调度"""
        try:
            self.window.after(0, lambda: func(*args, **kwargs))
        except Exception:
            pass

    def _setup_ui(self):
        ctk.CTkLabel(self.window, text="FH6Auto 自动化更新", font=ctk.CTkFont(weight="bold", size=18), text_color="#3498DB").pack(pady=(25, 10))
        
        self.lbl_version = ctk.CTkLabel(self.window, text=f"当前版本: v{CURRENT_VERSION}", text_color="gray", font=ctk.CTkFont(size=13))
        self.lbl_version.pack(pady=5)

        btn_frame = ctk.CTkFrame(self.window, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        ctk.CTkButton(btn_frame, text="检查更新", width=100, height=32, fg_color="#444444", hover_color="#555555", 
                      command=lambda: threading.Thread(target=self._check_update_logic, daemon=True).start()).pack(side="left", padx=5)
        
        ctk.CTkButton(btn_frame, text="前往 GitHub", width=100, height=32, fg_color="#2EA043", hover_color="#238636", 
                      command=lambda: webbrowser.open("https://github.com/AwuoeZYC/FH6Auto")).pack(side="left", padx=5)

    def _check_update_logic(self):
        self.ui_call(self.lbl_version.configure, text="正在连接 GitHub...", text_color="#3498DB")
        try:
            api_url = "https://api.github.com/repos/AwuoeZYC/FH6Auto/releases/latest"
            resp = requests.get(api_url, timeout=5, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                remote_ver = data.get("tag_name", "v0.0.0").replace("v", "")
                
                if parse_version(remote_ver) > parse_version(CURRENT_VERSION):
                    self.ui_call(self.lbl_version.configure, text=f"发现新版本 v{remote_ver}！", text_color="#2EA043")
                    
                    download_url = ""
                    for asset in data.get("assets", []):
                        if asset.get("name", "").endswith(".exe"):
                            download_url = asset.get("browser_download_url")
                            break
                            
                    if download_url:
                        self.ui_call(self._prompt_download, download_url, remote_ver)
                    else:
                        self.ui_call(self.lbl_version.configure, text="新版本未包含 exe 附件", text_color="#F39C12")
                else:
                    self.ui_call(self.lbl_version.configure, text=f"当前已是最新版本 (v{CURRENT_VERSION})", text_color="gray")
            else:
                self.ui_call(self.lbl_version.configure, text="检查更新失败：网络请求被拒", text_color="#DA3633")
        except Exception as e:
            self.ui_call(self.lbl_version.configure, text=f"异常: {str(e)[:20]}", text_color="#DA3633")

    def _prompt_download(self, download_url, remote_ver):
        from tkinter import messagebox
        # 把原始直连链接传给下载器，让它自己判断
        if messagebox.askyesno("发现新版本", f"检测到新版本 v{remote_ver}\n\n是否立即下载并热更新？\n(系统将自动尝试直连与加速节点)", parent=self.window):
            self._start_safe_download(download_url, remote_ver)

    def _start_safe_download(self, raw_url: str, version: str):
        dl_win = ctk.CTkToplevel(self.window)
        dl_win.title(f"正在下载 v{version}")
        dl_win.geometry("400x160")
        dl_win.resizable(False, False)
        dl_win.transient(self.window)
        
        # 居中
        dl_win.update_idletasks()
        x = self.window.winfo_x() + (self.window.winfo_width() - 400) // 2
        y = self.window.winfo_y() + (self.window.winfo_height() - 160) // 2
        dl_win.geometry(f"+{x}+{y}")
        
        lbl_status = ctk.CTkLabel(dl_win, text="准备下载...", font=ctk.CTkFont(weight="bold"))
        lbl_status.pack(pady=(20, 5))

        progress_bar = ctk.CTkProgressBar(dl_win, width=300)
        progress_bar.set(0)
        progress_bar.pack(pady=5)

        cancel_flag = {"is_cancelled": False}

        def cancel_download():
            cancel_flag["is_cancelled"] = True
            dl_win.destroy()

        ctk.CTkButton(dl_win, text="取消下载", fg_color="#DA3633", hover_color="#B02A37", width=100, command=cancel_download).pack(pady=10)

        def download_thread():
            try:
                current_exe_path = sys.executable 
                if not current_exe_path.lower().endswith("fh6auto.exe"):
                    self.ui_call(lbl_status.configure, text="[开发环境提示] 源码不支持热替换", text_color="#F39C12")
                    return

                tmp_file_path = current_exe_path + ".tmp"
                
                # 【核心设计 1】：全自动路由策略（直连 -> 节点1 -> 节点2）
                download_urls = [
                    raw_url,                                # 优先级 1: GitHub 直连
                    f"https://ghproxy.net/{raw_url}",       # 优先级 2: 稳定镜像源 A
                    f"https://ghp.ci/{raw_url}"             # 优先级 3: 备用镜像源 B
                ]
                
                download_success = False
                last_error = ""

                for target_url in download_urls:
                    if cancel_flag["is_cancelled"]:
                        break
                        
                    self.ui_call(lbl_status.configure, text=f"正在连接节点...", text_color="#3498DB")
                    # 【核心设计 2】：把动作同步打印到主界面的日志框，无惧 exe 打包！
                    self.parent.log(f"🔄 尝试下载节点: {target_url}")
                    
                    try:
                        resp = requests.get(target_url, stream=True, timeout=8, verify=False)
                        resp.raise_for_status()
                        total_size = int(resp.headers.get('content-length', 0))
                        
                        downloaded_size = 0
                        with open(tmp_file_path, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=8192):
                                if cancel_flag["is_cancelled"]:
                                    break
                                if chunk:
                                    f.write(chunk)
                                    downloaded_size += len(chunk)
                                    if total_size > 0:
                                        pct = downloaded_size / total_size
                                        self.ui_call(progress_bar.set, pct)
                                        # 【核心修复】：将原本崩溃的 parent.after 换成 ui_call，完美支持 kwargs！
                                        self.ui_call(lbl_status.configure, text=f"下载进度: {int(pct*100)}%", text_color="#F1C40F")

                        if cancel_flag["is_cancelled"]:
                            if os.path.exists(tmp_file_path): os.remove(tmp_file_path)
                            return
                            
                        download_success = True
                        break  # 如果没报错并且下载完了，直接跳出循环！

                    except Exception as e:
                        last_error = str(e)
                        self.parent.log(f"⚠️ 该节点下载失败: {last_error[:80]}... 尝试切换。")
                        continue # 当前 URL 失败，静默继续尝试下一个 URL

                if not download_success and not cancel_flag["is_cancelled"]:
                    raise Exception(f"所有节点均连接失败。最后一次报错: {last_error}")

                self.ui_call(lbl_status.configure, text="下载完成！正在部署并重启...", text_color="#2EA043")
                self.parent.log("✅ 更新包下载完成，准备唤醒外部 Updater...")
                import time; time.sleep(1.0)
                self.ui_call(dl_win.destroy)

                import shutil
                from tkinter import messagebox
                bundled_updater = get_asset_path("Updater.exe")
                external_updater = os.path.join(os.environ.get("TEMP", "C:\\"), "FH6_Updater.exe")
                
                if bundled_updater and os.path.exists(bundled_updater):
                    shutil.copy2(bundled_updater, external_updater)
                    import subprocess
                    subprocess.Popen([external_updater, str(os.getpid()), current_exe_path, tmp_file_path], creationflags=subprocess.CREATE_NO_WINDOW)
                    os._exit(0)
                else:
                    self.parent.log("🚨 缺少核心更新组件(Updater.exe)，无法完成热替换！")
                    self.ui_call(messagebox.showerror, "错误", "缺少更新组件(Updater.exe)，无法热替换！")

            except Exception as e:
                # 最终兜底：如果有任何意料之外的错误，全部塞进主窗口的日志里
                if not cancel_flag["is_cancelled"]:
                    self.parent.log(f"🚨 致命更新异常: {e}")
                    self.ui_call(lbl_status.configure, text="下载失败", text_color="#DA3633")
                    
        import threading
        threading.Thread(target=download_thread, daemon=True).start()