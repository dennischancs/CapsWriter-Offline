import ApplicationServices
import AVFoundation
import CoreGraphics

enum Permissions {
    static func promptAll() {
        AVCaptureDevice.requestAccess(for: .audio) { _ in }
        let key = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
        let options = [key: true] as CFDictionary
        _ = AXIsProcessTrustedWithOptions(options)
        if !CGPreflightListenEventAccess() {
            _ = CGRequestListenEventAccess()
        }
    }

    static func microphoneAllowed() -> Bool {
        AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
    }

    static func accessibilityAllowed() -> Bool {
        AXIsProcessTrusted()
    }

    static func listenAllowed() -> Bool {
        CGPreflightListenEventAccess()
    }
}
