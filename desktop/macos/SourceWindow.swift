// macOS owns the window and folder picker; the existing Reprise service owns data.
import AppKit
import WebKit

enum DesktopError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case let .message(value) = self { return value }; return nil }
}

final class RepriseApp: NSObject, NSApplicationDelegate, WKNavigationDelegate,
    WKUIDelegate, WKScriptMessageHandlerWithReply, WKDownloadDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var progress: NSProgressIndicator!
    private var status: NSTextField!
    private var serviceURL: URL?
    private var ownedInstance: String?
    private var opening = false
    private var quitting = false
    private var pickerOpen = false
    private var launchAddress: String? { argument("--url") }
    private func argument(_ name: String) -> String? {
        let args = CommandLine.arguments
        guard let i = args.firstIndex(of: name), i + 1 < args.count else { return nil }
        return args[i + 1]
    }
    private var chinese: Bool {
        if let address = launchAddress,
           let language = URLComponents(string: address)?.queryItems?.first(where: { $0.name == "lang" })?.value {
            return language == "zh"
        }
        if let data = try? Data(contentsOf: resources.appendingPathComponent("source-launch.json")),
           let record = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
           let language = record["language"] as? String, ["zh", "en"].contains(language) {
            return language == "zh"
        }
        return Locale.preferredLanguages.first?.hasPrefix("zh") ?? false
    }
    private func reportWindow(_ result: [String: String]) {
        guard let path = argument("--ready-file") else { return }
        if let data = try? JSONSerialization.data(withJSONObject: result) {
            try? data.write(to: URL(fileURLWithPath: path), options: .atomic)
        }
    }
    private var resources: URL { Bundle.main.resourceURL! }
    private var dataPath: String? {
        let args = CommandLine.arguments
        guard let i = args.firstIndex(of: "--data"), i + 1 < args.count else { return nil }
        return args[i + 1]
    }
    private func text(_ zh: String, _ en: String) -> String { chinese ? zh : en }

    func applicationDidFinishLaunching(_ notification: Notification) {
        if let icon = NSImage(contentsOf: resources.appendingPathComponent("reprise-icon-1024.png")) {
            NSApp.applicationIconImage = icon
        }
        buildMenu()
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.userContentController.addScriptMessageHandler(self, contentWorld: .page, name: "repriseDesktop")
        let bridge = """
        Object.defineProperty(window, 'RepriseDesktop', {value: Object.freeze({
          chooseFolder: () => window.webkit.messageHandlers.repriseDesktop.postMessage({action: 'choose-folder'}),
          chooseBackup: (save = false) => window.webkit.messageHandlers.repriseDesktop.postMessage({action: save ? 'save-backup' : 'open-backup'}),
          quit: () => window.webkit.messageHandlers.repriseDesktop.postMessage({action: 'quit'})
        }), writable: false, configurable: false});
        """
        config.userContentController.addUserScript(WKUserScript(source: bridge, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.autoresizingMask = [.width, .height]
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 860),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Reprise"
        window.minSize = NSSize(width: 900, height: 620)
        window.isReleasedWhenClosed = false
        window.contentView = webView
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        progress = NSProgressIndicator(frame: NSRect(x: 0, y: 0, width: 28, height: 28))
        progress.style = .spinning
        progress.translatesAutoresizingMaskIntoConstraints = false
        status = NSTextField(labelWithString: text("正在打开网页稿件…", "Opening your website drafts…"))
        status.font = .systemFont(ofSize: 15)
        status.translatesAutoresizingMaskIntoConstraints = false
        webView.addSubview(progress)
        webView.addSubview(status)
        NSLayoutConstraint.activate([
            progress.centerXAnchor.constraint(equalTo: webView.centerXAnchor),
            progress.centerYAnchor.constraint(equalTo: webView.centerYAnchor, constant: -16),
            status.centerXAnchor.constraint(equalTo: webView.centerXAnchor),
            status.topAnchor.constraint(equalTo: progress.bottomAnchor, constant: 14)
        ])
        start()
    }

    private func buildMenu() {
        let menu = NSMenu()
        let application = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: text("关于 Reprise", "About Reprise"), action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: text("隐藏 Reprise", "Hide Reprise"), action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: text("退出 Reprise", "Quit Reprise"), action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        application.submenu = appMenu
        menu.addItem(application)
        let edit = NSMenuItem(title: text("编辑", "Edit"), action: nil, keyEquivalent: "")
        let editMenu = NSMenu(title: edit.title)
        editMenu.addItem(withTitle: text("撤销", "Undo"), action: Selector(("undo:")), keyEquivalent: "z")
        editMenu.addItem(withTitle: text("剪切", "Cut"), action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: text("复制", "Copy"), action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: text("粘贴", "Paste"), action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: text("全选", "Select All"), action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        edit.submenu = editMenu
        menu.addItem(edit)
        NSApp.mainMenu = menu
    }

    private func helper(_ command: String, instance: String? = nil) throws -> [String: Any] {
        let manifestURL = resources.appendingPathComponent("source-launch.json")
        let raw = try JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL))
        guard let manifest = raw as? [String: Any], manifest["schema"] as? Int == 1,
              let python = manifest["python"] as? String, python.hasPrefix("/"),
              let entry = manifest["entry"] as? String, entry.hasPrefix("/"),
              let directory = manifest["data"] as? String, directory.hasPrefix("/"),
              FileManager.default.isExecutableFile(atPath: python),
              FileManager.default.fileExists(atPath: entry) else {
            throw DesktopError.message("Reopen Reprise through its installed Skill to reconnect this window.")
        }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = ["-I", "-S", "-B", entry, command, "--data", directory]
        if let language = manifest["language"] as? String, ["zh", "en"].contains(language) {
            process.arguments! += ["--lang", language]
        }
        if let project = manifest["project"] as? String, !project.isEmpty {
            process.arguments! += ["--project", project]
        }
        if let identifier = instance { process.arguments! += ["--instance-id", identifier] }
        process.currentDirectoryURL = resources
        var environment = ProcessInfo.processInfo.environment
        for key in Array(environment.keys) where key.hasPrefix("PYTHON") || key.hasPrefix("DYLD_") || key.hasPrefix("NODE_") {
            environment.removeValue(forKey: key)
        }
        environment["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
        process.environment = environment
        let output = Pipe(), errors = Pipe()
        process.standardOutput = output
        process.standardError = errors
        process.standardInput = FileHandle.nullDevice
        try process.run()
        let timeout = DispatchWorkItem { if process.isRunning { process.terminate() } }
        DispatchQueue.global().asyncAfter(deadline: .now() + 45, execute: timeout)
        let stdout = output.fileHandleForReading.readDataToEndOfFile()
        let stderr = errors.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        timeout.cancel()
        guard process.terminationStatus == 0 else {
            let detail = String(data: stderr, encoding: .utf8) ?? "The bundled service did not start."
            throw DesktopError.message(String(detail.prefix(5000)))
        }
        guard let result = try JSONSerialization.jsonObject(with: stdout) as? [String: Any] else {
            throw DesktopError.message("Reprise did not return a valid startup result.")
        }
        return result
    }

    private func start() {
        // The source Skill has already verified and opened the local service.
        // URL mode reuses this window without requiring a bundled Python runtime.
        if let address = launchAddress {
            guard let parts = URLComponents(string: address), parts.scheme == "http",
                  parts.host == "127.0.0.1", parts.port != nil,
                  parts.user == nil, parts.password == nil, parts.path == "/",
                  let url = parts.url else {
                showFailure("Reprise did not return a verified local address."); return
            }
            serviceURL = url
            progress.startAnimation(nil)
            webView.load(URLRequest(url: url))
            return
        }
        opening = true
        progress.startAnimation(nil)
        DispatchQueue.global(qos: .userInitiated).async {
            let result = Result { try self.helper("open") }
            DispatchQueue.main.async {
                self.opening = false
                switch result {
                case let .success(record):
                    if record["reused"] as? Bool == false { self.ownedInstance = record["instance_id"] as? String }
                    if self.quitting { self.stopOwnedService(); return }
                    guard let address = record["url"] as? String, var components = URLComponents(string: address),
                          components.scheme == "http", components.host == "127.0.0.1", components.port != nil else {
                        self.showFailure("Reprise did not return a verified local address."); return
                    }
                    components.queryItems = (components.queryItems ?? []).filter { $0.name != "lang" }
                        + [URLQueryItem(name: "lang", value: self.chinese ? "zh" : "en")]
                    self.serviceURL = components.url!
                    self.webView.load(URLRequest(url: self.serviceURL!))
                case let .failure(error):
                    if self.quitting { NSApp.reply(toApplicationShouldTerminate: true) }
                    else { self.showFailure(error.localizedDescription) }
                }
            }
        }
    }

    private func showFailure(_ detail: String) {
        reportWindow(["status": "failed", "error": detail])
        progress.stopAnimation(nil)
        status.stringValue = text("Reprise 未能打开", "Reprise could not open")
        let alert = NSAlert()
        alert.messageText = text("未能打开 Reprise", "Could not open Reprise")
        alert.informativeText = text("请保留完整的 Reprise.app。已保存的稿件不会因此被删除。\n\n", "Keep the complete Reprise.app. Your saved drafts are retained.\n\n") + detail
        alert.addButton(withTitle: text("退出", "Quit"))
        alert.runModal()
        NSApp.terminate(nil)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if quitting { return .terminateLater }
        if !opening && ownedInstance == nil { return .terminateNow }
        quitting = true
        if !opening { stopOwnedService() }
        return .terminateLater
    }

    private func stopOwnedService() {
        guard let instance = ownedInstance else { NSApp.reply(toApplicationShouldTerminate: true); return }
        status.stringValue = text("正在停止本次预览…", "Stopping this session’s previews…")
        DispatchQueue.global(qos: .userInitiated).async {
            let result = Result { try self.helper("shutdown", instance: instance) }
            DispatchQueue.main.async {
                switch result {
                case let .success(record):
                    if record["stopped"] as? Bool == true || record["reason"] as? String == "different-instance" {
                        self.ownedInstance = nil
                        NSApp.reply(toApplicationShouldTerminate: true)
                    } else { self.shutdownFailed("Service shutdown was not confirmed.") }
                case let .failure(error): self.shutdownFailed(error.localizedDescription)
                }
            }
        }
    }

    private func shutdownFailed(_ detail: String) {
        quitting = false
        window.makeKeyAndOrderFront(nil)
        let alert = NSAlert()
        alert.messageText = text("尚未确认预览已停止", "Preview shutdown is not confirmed")
        alert.informativeText = detail
        alert.addButton(withTitle: text("返回 Reprise", "Return to Reprise"))
        alert.runModal()
        NSApp.reply(toApplicationShouldTerminate: false)
    }

    private func trusted(_ url: URL?) -> Bool {
        guard let url = url, let service = serviceURL else { return false }
        return url.scheme == service.scheme && url.host == service.host && url.port == service.port
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage,
                               replyHandler: @escaping (Any?, String?) -> Void) {
        guard message.frameInfo.isMainFrame, trusted(message.frameInfo.request.url),
              let value = message.body as? [String: String] else {
            replyHandler(nil, "Only the Reprise window can use desktop controls."); return
        }
        switch value["action"] {
        case "choose-folder":
            guard !pickerOpen else { replyHandler(["status": "error", "reason": "picker-busy"], nil); return }
            pickerOpen = true
            let panel = NSOpenPanel()
            panel.canChooseFiles = false
            panel.canChooseDirectories = true
            panel.allowsMultipleSelection = false
            panel.canCreateDirectories = false
            panel.prompt = text("选择网页文件夹", "Choose website folder")
            panel.message = text("选择你正在用 AI 或编辑器修改的网页项目。", "Choose the website project you edit with AI or an editor.")
            panel.beginSheetModal(for: window) { response in
                self.pickerOpen = false
                if response == .OK, let url = panel.url {
                    replyHandler(["status": "selected", "path": url.path, "backend": "appkit"], nil)
                } else { replyHandler(["status": "cancelled", "backend": "appkit"], nil) }
            }
        case "save-backup", "open-backup":
            guard !pickerOpen else { replyHandler(["status": "error", "reason": "picker-busy"], nil); return }
            pickerOpen = true
            let saving = value["action"] == "save-backup"
            let panel: NSSavePanel
            if saving {
                let save = NSSavePanel()
                save.nameFieldStringValue = "Reprise.reprise-backup.zip"
                panel = save
            } else {
                let open = NSOpenPanel()
                open.canChooseFiles = true
                open.canChooseDirectories = false
                open.allowsMultipleSelection = false
                panel = open
            }
            panel.allowedFileTypes = ["zip"]
            panel.title = text(saving ? "保存备份" : "导入备份", saving ? "Save backup" : "Import backup")
            panel.prompt = text(saving ? "保存" : "导入", saving ? "Save" : "Import")
            panel.beginSheetModal(for: window) { response in
                self.pickerOpen = false
                if response == .OK, let url = panel.url {
                    replyHandler(["status": "selected", "path": url.path, "backend": "appkit"], nil)
                } else { replyHandler(["status": "cancelled", "backend": "appkit"], nil) }
            }
        case "quit":
            replyHandler(["status": "closing"], nil)
            DispatchQueue.main.async { NSApp.terminate(nil) }
        default: replyHandler(nil, "Unknown desktop control.")
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        progress.stopAnimation(nil)
        progress.isHidden = true
        status.isHidden = true
        reportWindow(["status": "ready", "url": serviceURL?.absoluteString ?? ""])
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if !quitting { showFailure(error.localizedDescription) }
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if action.targetFrame?.isMainFrame == false { decisionHandler(.allow); return }
        if trusted(action.request.url) {
            decisionHandler(action.shouldPerformDownload ? .download : .allow)
        } else {
            if action.navigationType == .linkActivated, let url = action.request.url,
               ["https", "http"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
            decisionHandler(.cancel)
        }
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url, ["http", "https"].contains(url.scheme ?? ""), action.navigationType == .linkActivated {
            NSWorkspace.shared.open(url)
        }
        return nil
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        decisionHandler(response.canShowMIMEType ? .allow : .download)
    }
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String,
                  completionHandler: @escaping (URL?) -> Void) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = (suggestedFilename as NSString).lastPathComponent
        panel.beginSheetModal(for: window) { result in completionHandler(result == .OK ? panel.url : nil) }
    }
}

let app = NSApplication.shared
let delegate = RepriseApp()
app.setActivationPolicy(.regular)
app.delegate = delegate
app.run()
