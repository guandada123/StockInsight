/// Python API 进程管理 — 自动启动/停止 FastAPI 后端
use std::fs::{self, File};
use std::process::Stdio;
use std::sync::Mutex;
use tokio::process::Command;
use tokio::time::{sleep, Duration};

static PYTHON_CHILD: Mutex<Option<tokio::process::Child>> = Mutex::new(None);

const HEALTH_URL: &str = "http://127.0.0.1:8765/api/health";

fn find_python() -> String {
    // 优先 .venv，回退系统 python
    for c in &[r".\.venv\Scripts\python.exe", r"..\.venv\Scripts\python.exe"] {
        if std::path::Path::new(c).exists() {
            return c.to_string();
        }
    }
    for cmd in &["python", "python3"] {
        if std::process::Command::new(cmd).arg("--version")
            .stdout(Stdio::null()).stderr(Stdio::null()).status().is_ok()
        {
            return cmd.to_string();
        }
    }
    "python".to_string()
}

fn find_project_root() -> std::path::PathBuf {
    let dev = std::env::current_dir().unwrap_or_default()
        .parent().map(|p| p.to_path_buf()).unwrap_or_default();
    if dev.join("cli.py").exists() { return dev; }
    if let Ok(exe) = std::env::current_exe() {
        for a in exe.ancestors().take(4) {
            if a.join("cli.py").exists() { return a.to_path_buf(); }
        }
    }
    std::env::current_dir().unwrap_or_default()
}

pub async fn start_python_api() -> Result<(), String> {
    // 杀掉占用 8765 端口的旧进程（跨平台）
    #[cfg(target_os = "windows")]
    let _ = std::process::Command::new("cmd")
        .args(["/c", "for /f \"tokens=5\" %a in ('netstat -ano ^| findstr :8765 ^| findstr LISTENING') do taskkill /F /PID %a >nul 2>&1"])
        .stdout(Stdio::null()).stderr(Stdio::null())
        .status();
    #[cfg(not(target_os = "windows"))]
    let _ = std::process::Command::new("sh")
        .args(["-c", "lsof -ti:8765 2>/dev/null | xargs kill -9 2>/dev/null"])
        .stdout(Stdio::null()).stderr(Stdio::null())
        .status();

    let python = find_python();
    let root = find_project_root();
    println!("[sidecar] Project root: {}", root.display());
    println!("[sidecar] Launching: {} -m backend.main", python);

    // 确保 logs/ 目录存在
    let log_dir = root.join("logs");
    let _ = fs::create_dir_all(&log_dir);
    // stderr 写日志文件方便排查
    let log_file = File::create(log_dir.join("sidecar_python.log"))
        .unwrap_or_else(|_| std::fs::File::create("sidecar_python.log").unwrap());

    let child = Command::new(&python)
        .args(["-m", "backend.main"])
        .current_dir(&root)
        .stdout(Stdio::from(log_file.try_clone().unwrap()))
        .stderr(Stdio::from(log_file))
        .kill_on_drop(true)
        .spawn()
        .map_err(|e| format!("无法启动 Python ({python}): {e}. 请确认 Python 3.9+ 已安装"))?;

    if let Ok(mut g) = PYTHON_CHILD.lock() { *g = Some(child); }

    for i in 1..=30 {
        sleep(Duration::from_secs(1)).await;
        if reqwest::get(HEALTH_URL).await.map(|r| r.status().is_success()).unwrap_or(false) {
            println!("[sidecar] Python API ready ({}s)", i);
            return Ok(());
        }
    }
    Err("Python API 启动超时 (30秒)，请查看 logs/sidecar_python.log".to_string())
}

pub fn stop_python_api() {
    if let Ok(mut g) = PYTHON_CHILD.lock() {
        if let Some(c) = g.take() {
            println!("[sidecar] Stopping Python API...");
            drop(c); // kill_on_drop 生效
        }
    }
}
