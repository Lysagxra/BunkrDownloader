import AppKit
let path = CommandLine.arguments[1]
try FileManager.default.createDirectory(atPath: path, withIntermediateDirectories: true)
for size in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let pixels = size * scale
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels,
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
        let s = CGFloat(pixels) / 1024
        let transform = NSAffineTransform(); transform.scale(by: s); transform.concat()
        let rect = NSRect(x: 55, y: 55, width: 914, height: 914)
        let shape = NSBezierPath(roundedRect: rect, xRadius: 210, yRadius: 210)
        NSGradient(starting: NSColor(red: 0.05, green: 0.69, blue: 0.66, alpha: 1), ending: NSColor(red: 0.02, green: 0.27, blue: 0.34, alpha: 1))!.draw(in: shape, angle: -70)
        NSColor.white.withAlphaComponent(0.12).setFill()
        NSBezierPath(roundedRect: NSRect(x: 166, y: 173, width: 692, height: 280), xRadius: 85, yRadius: 85).fill()
        let arrow = NSBezierPath()
        arrow.move(to: NSPoint(x: 512, y: 767)); arrow.line(to: NSPoint(x: 512, y: 360))
        arrow.move(to: NSPoint(x: 350, y: 517)); arrow.line(to: NSPoint(x: 512, y: 355)); arrow.line(to: NSPoint(x: 674, y: 517))
        arrow.move(to: NSPoint(x: 315, y: 265)); arrow.line(to: NSPoint(x: 709, y: 265))
        arrow.lineWidth = 67; arrow.lineCapStyle = .round; arrow.lineJoinStyle = .round
        NSColor.white.setStroke(); arrow.stroke()
        NSGraphicsContext.restoreGraphicsState()
        let name = "icon_\(size)x\(size)\(scale == 2 ? "@2x" : "").png"
        try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: path).appendingPathComponent(name))
    }
}
