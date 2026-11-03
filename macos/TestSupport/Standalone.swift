// Runs the same XCTest methods on Macs with only Command Line Tools installed.
import Foundation
class XCTestCase {}
func XCTAssertEqual<T: Equatable>(_ lhs: @autoclosure () throws -> T, _ rhs: @autoclosure () throws -> T, _ message: String = "") rethrows {
    let a = try lhs(), b = try rhs()
    precondition(a == b, "Expected \(a) == \(b). \(message)")
}
func XCTAssertNil<T>(_ value: T?, _ message: String = "") { precondition(value == nil, message) }
func XCTAssertNotNil<T>(_ value: T?) { precondition(value != nil) }
func XCTAssertTrue(_ value: Bool) { precondition(value) }
func XCTFail(_ message: String) { fatalError(message) }

@main struct NativeTests {
    @MainActor static func main() async throws {
        let tests = BunkrTests()
        try tests.testDiagnosticRotationAndRedaction()
        tests.testValidURLs()
        tests.testInvalidURLs()
        try tests.testQueuePersistsAndInterruptedJobNeedsRetry()
        try tests.testCorruptQueueIsPreserved()
        try tests.testRequestFiltersRemoveEmptyEntries()
        let lifecycle = EngineLifecycleTests()
        try await lifecycle.testSuccessfulEngineDrainsLastResultBeforeExit()
        try await lifecycle.testCleanExitWithoutResultIsFailure()
        try await lifecycle.testCancellationDoesNotStartNextJob()
        print("Passed 9 native tests (including 3 subprocess lifecycle tests).")
    }
}
