// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "Bunkr",
    platforms: [.macOS("27.0")],
    products: [.executable(name: "Bunkr", targets: ["Bunkr"])],
    targets: [
        .executableTarget(name: "Bunkr", path: "Sources"),
        .testTarget(name: "BunkrTests", dependencies: ["Bunkr"], path: "Tests")
    ],
    swiftLanguageModes: [.v5]
)
