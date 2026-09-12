// 대시보드 확인용 스크린샷: WebKit으로 URL을 열어 JS까지 실행한 뒤 PNG로 저장.
// usage: webshot <url> <out.png> [width=1400] [height=1000] [wait-seconds=4]
// 빌드: swiftc -O -o scripts/webshot scripts/webshot.swift
import Cocoa
import WebKit

let args = CommandLine.arguments
guard args.count >= 3, let url = URL(string: args[1]) else {
    FileHandle.standardError.write("usage: webshot <url> <out.png> [width] [height] [wait-seconds]\n".data(using: .utf8)!)
    exit(2)
}
let out = args[2]
let width = args.count > 3 ? Double(args[3]) ?? 1400 : 1400
let height = args.count > 4 ? Double(args[4]) ?? 1000 : 1000
let wait = args.count > 5 ? Double(args[5]) ?? 4 : 4

final class Shot: NSObject, WKNavigationDelegate {
    let view: WKWebView
    init(width: Double, height: Double) {
        let cfg = WKWebViewConfiguration()
        view = WKWebView(frame: NSRect(x: 0, y: 0, width: width, height: height), configuration: cfg)
        super.init()
        view.navigationDelegate = self
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        DispatchQueue.main.asyncAfter(deadline: .now() + wait) {
            let c = WKSnapshotConfiguration()
            c.rect = NSRect(x: 0, y: 0, width: width, height: height)
            webView.takeSnapshot(with: c) { img, err in
                guard let img = img, let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
                      let png = rep.representation(using: .png, properties: [:]) else {
                    FileHandle.standardError.write("snapshot failed: \(String(describing: err))\n".data(using: .utf8)!); exit(1)
                }
                try? png.write(to: URL(fileURLWithPath: out))
                exit(0)
            }
        }
    }
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        FileHandle.standardError.write("load failed: \(error)\n".data(using: .utf8)!); exit(1)
    }
}
let app = NSApplication.shared
app.setActivationPolicy(.prohibited)
let shot = Shot(width: width, height: height)
shot.view.load(URLRequest(url: url))
app.run()
