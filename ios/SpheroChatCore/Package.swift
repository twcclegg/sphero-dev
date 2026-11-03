// swift-tools-version:5.9
// The parts of the iPad app that don't need UIKit/SwiftUI: the server's message
// format, the HTTP client, and the Python highlighter. Builds and tests on Linux too.
import PackageDescription

let package = Package(
    name: "SpheroChatCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "SpheroChatCore", targets: ["SpheroChatCore"])],
    targets: [
        .target(name: "SpheroChatCore"),
        .testTarget(name: "SpheroChatCoreTests", dependencies: ["SpheroChatCore"]),
    ]
)
