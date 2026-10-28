// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "CapsWriterShell",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "CapsWriter", targets: ["CapsWriter"]),
    ],
    targets: [
        .target(name: "CapsWriterCore"),
        .executableTarget(
            name: "CapsWriter",
            dependencies: ["CapsWriterCore"],
            linkerSettings: [
                .linkedFramework("AppKit"),
                .linkedFramework("SwiftUI"),
                .linkedFramework("AVFoundation"),
                .linkedFramework("ApplicationServices"),
                .linkedFramework("CoreGraphics"),
                .linkedFramework("CFNetwork"),
            ]
        ),
        .testTarget(name: "CapsWriterCoreTests", dependencies: ["CapsWriterCore"]),
    ]
)
