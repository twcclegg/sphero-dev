import Foundation
import XCTest
@testable import SpheroChatCore

final class HighlighterTests: XCTestCase {
    let program = """
    # Drives a square.
    @decorated
    async def start_program():
        set_main_led({'r': 0, 'g': 0, 'b': 255})
        for side in range(4):
            await roll(side * 90, 80, 1.5)  # one side
        speak(f"done {3.5}", True)
        s = \"\"\"multi
    line\"\"\"
    """

    func testRoundTrips() {
        XCTAssertEqual(PythonHighlighter.tokenize(program).map(\.text).joined(), program)
        XCTAssertEqual(PythonHighlighter.tokenize("x = 'unterminated\ny'").map(\.text).joined(),
                       "x = 'unterminated\ny'")
    }

    func testKinds() {
        let tokens = PythonHighlighter.tokenize(program)
        func kind(_ text: String) -> TokenKind? { tokens.first { $0.text == text }?.kind }
        XCTAssertEqual(kind("# Drives a square."), .comment)
        XCTAssertEqual(kind("@decorated"), .decorator)
        XCTAssertEqual(kind("async"), .keyword)
        XCTAssertEqual(kind("start_program"), .definition)
        XCTAssertEqual(kind("set_main_led"), .edu)
        XCTAssertEqual(kind("'r'"), .string)
        XCTAssertEqual(kind("range"), .builtin)
        XCTAssertEqual(kind("1.5"), .number)
        XCTAssertEqual(kind("f\"done {3.5}\""), .string)
        XCTAssertEqual(kind("True"), .keyword)
        XCTAssertEqual(kind("\"\"\"multi\nline\"\"\""), .string)
        XCTAssertEqual(kind("# one side"), .comment)
    }
}

final class ModelTests: XCTestCase {
    func testDecodesServerMessages() throws {
        let json = """
        {"conversation": "abc", "messages": [
          {"role": "status", "parts": [{"type": "text", "text": "simulating"}]},
          {"role": "assistant", "parts": [
            {"type": "text", "text": "**Square**"},
            {"type": "code", "language": "python", "title": "Square", "code": "pass"},
            {"type": "chart", "title": "Path", "kind": "path", "x_label": "x", "y_label": "y",
             "series": [{"name": "path", "points": [[0, 0], [1.5, 2]]}]},
            {"type": "table", "title": "Sensors", "columns": ["t", "x"], "rows": [["0.0", "1"]]},
            {"type": "video", "url": "..."}
          ]}
        ]}
        """
        let r = try JSONDecoder.server.decode(ChatResponse.self, from: Data(json.utf8))
        XCTAssertEqual(r.conversation, "abc")
        XCTAssertEqual(r.messages[0].role, .status)
        let parts = r.messages[1].parts
        XCTAssertEqual(parts[1], .code(CodePart(language: "python", title: "Square", code: "pass")))
        guard case .chart(let chart) = parts[2] else { return XCTFail("no chart") }
        XCTAssertEqual(chart.kind, .path)
        XCTAssertEqual(chart.xLabel, "x")
        XCTAssertEqual(chart.series[0].points[1], [1.5, 2])
        guard case .table(let table) = parts[3] else { return XCTFail("no table") }
        XCTAssertEqual(table.csv, "t,x\n0.0,1\n")
        XCTAssertEqual(parts[4], .unknown("video"))
        XCTAssertEqual(r.messages[1].code?.title, "Square")
    }

    func testHistoryRoundTrips() throws {
        let m = ChatMessage(role: .assistant, parts: [
            .text("hi"), .code(CodePart(code: "x = 1")),
            .chart(ChartPart(title: "t", kind: .line, xLabel: "s", yLabel: "cm/s",
                             series: [.init(name: "v", points: [[0, 1]])])),
            .table(TablePart(columns: ["a"], rows: [["1"]])),
        ])
        let data = try JSONEncoder().encode([m])
        XCTAssertEqual(try JSONDecoder().decode([ChatMessage].self, from: data), [m])
    }

    func testServerAddress() {
        XCTAssertEqual(SpheroServer(address: "sphero.clegg.dev", token: "t")?.baseURL
                        .absoluteString, "https://sphero.clegg.dev:8765")
        XCTAssertEqual(SpheroServer(address: "http://192.168.1.20", token: "t")?.baseURL
                        .absoluteString, "http://192.168.1.20:8765")
        XCTAssertEqual(SpheroServer(address: "http://laptop.local:9000", token: "t")?.baseURL
                        .absoluteString, "http://laptop.local:9000")
        XCTAssertEqual(SpheroServer(address: "192.168.1.20", token: " t ")?.token, "t")
        XCTAssertNil(SpheroServer(address: "  ", token: "t"))
    }
}

final class MarkdownTests: XCTestCase {
    func testSplitsFences() {
        let parts = Markdown.split("Try this:\n\n```python\nset_speed(50)\n```\nThen run it.")
        XCTAssertEqual(parts, [.text("Try this:"), .code(CodePart(code: "set_speed(50)")),
                               .text("Then run it.")])
        XCTAssertEqual(Markdown.split("plain"), [.text("plain")])
        XCTAssertEqual(Markdown.split("```\nx = 1"), [.code(CodePart(code: "x = 1"))])
    }
}

/// Against a running `sphero-dev serve` whose Claude proposes a program on the first
/// message (see `tests/serve_fixture.py`). Skipped unless SPHERO_TEST_SERVER is set.
final class LiveServerTests: XCTestCase {
    func testChatRunAndExport() async throws {
        let env = ProcessInfo.processInfo.environment
        guard let address = env["SPHERO_TEST_SERVER"], let token = env["SPHERO_TEST_TOKEN"] else {
            throw XCTSkip("SPHERO_TEST_SERVER not set")
        }
        let server = try XCTUnwrap(SpheroServer(address: address, token: token))
        let health = try await server.health()
        XCTAssertTrue(health.ok)
        do {
            _ = try await SpheroServer(address: address, token: "wrong")!.health()
            XCTFail("wrong token accepted")
        } catch let e as ServerError {
            XCTAssertEqual(e.status, 401)
        }
        let reply = try await server.chat(conversation: nil, text: "drive forward")
        XCTAssertNotNil(reply.messages.last?.code)
        let run = try await server.run(conversation: reply.conversation)
        XCTAssertTrue(run[0].parts.contains { if case .table = $0 { return true }; return false })
        let (name, data) = try await server.programLab(conversation: reply.conversation)
        XCTAssertEqual(name, "forward.lab")
        XCTAssertFalse(data.isEmpty)
        try await server.stop()
    }
}
