#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod sidecar;

use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let handle = app.handle().clone();

            // 启动 Python API 子进程
            tauri::async_runtime::spawn(async move {
                println!("[tauri] Starting Python API sidecar...");
                match sidecar::start_python_api().await {
                    Ok(()) => {
                        println!("[tauri] Python API is ready");
                        if let Some(window) = handle.get_webview_window("main") {
                            let _ = window.eval("if(window.__onApiReady)window.__onApiReady()");
                        }
                    }
                    Err(e) => {
                        eprintln!("[tauri] Failed to start Python API: {}", e);
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|_window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                println!("[tauri] Window closed, stopping sidecar...");
                sidecar::stop_python_api();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
